import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Columns3, Expand, Focus, Rows3 } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { EstimatedBallTrajectory } from "../../services/ballTrajectoryVisualization";

type CameraView = "oblique" | "top" | "side" | "end";

interface BallTrajectorySceneProps {
  trajectories: EstimatedBallTrajectory[];
  selectedShotId: string | null;
  onSelectShot: (shotId: string | null) => void;
  onWebGlError: (message: string) => void;
}

const VIEW_CONFIG: Record<CameraView, { position: [number, number, number]; label: string; icon: typeof Box }> = {
  oblique: { position: [30, 28, 36], label: "斜视", icon: Box },
  top: { position: [0.01, 55, 0.01], label: "俯视", icon: Rows3 },
  side: { position: [40, 12, 0], label: "侧视", icon: Columns3 },
  end: { position: [0, 14, 44], label: "端线", icon: Focus },
};

const DIRECTION_COLORS = {
  "near-to-far": "#25B86A",
  "far-to-near": "#F04438",
} as const;

function courtVector(xFt: number, heightFt: number, yFt: number): THREE.Vector3 {
  return new THREE.Vector3(xFt - 10, heightFt, yFt - 22);
}

function addCourtLine(group: THREE.Group, points: Array<[number, number]>, material: THREE.LineBasicMaterial) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points.map(([x, z]) => new THREE.Vector3(x, 0.035, z)));
  group.add(new THREE.Line(geometry, material));
}

function buildCourt(): THREE.Group {
  const group = new THREE.Group();
  group.name = "court";

  const surface = new THREE.Mesh(
    new THREE.PlaneGeometry(20, 44),
    new THREE.MeshStandardMaterial({ color: "#E4E9E5", roughness: 0.9, metalness: 0 }),
  );
  surface.rotation.x = -Math.PI / 2;
  surface.receiveShadow = true;
  group.add(surface);

  const apron = new THREE.Mesh(
    new THREE.PlaneGeometry(28, 54),
    new THREE.MeshStandardMaterial({ color: "#F4F6F4", roughness: 1 }),
  );
  apron.rotation.x = -Math.PI / 2;
  apron.position.y = -0.04;
  group.add(apron);

  const boundaryMaterial = new THREE.LineBasicMaterial({ color: "#5E6762" });
  const innerMaterial = new THREE.LineBasicMaterial({ color: "#8C9690" });
  addCourtLine(group, [[-10, -22], [10, -22], [10, 22], [-10, 22], [-10, -22]], boundaryMaterial);
  addCourtLine(group, [[-10, -7], [10, -7]], innerMaterial);
  addCourtLine(group, [[-10, 7], [10, 7]], innerMaterial);
  addCourtLine(group, [[0, -22], [0, -7]], innerMaterial);
  addCourtLine(group, [[0, 7], [0, 22]], innerMaterial);

  const kitchenMaterial = new THREE.MeshStandardMaterial({ color: "#D6DDD8", transparent: true, opacity: 0.65 });
  const kitchen = new THREE.Mesh(new THREE.PlaneGeometry(20, 14), kitchenMaterial);
  kitchen.rotation.x = -Math.PI / 2;
  kitchen.position.y = 0.012;
  group.add(kitchen);

  const net = new THREE.Mesh(
    new THREE.BoxGeometry(20.6, 2.85, 0.09),
    new THREE.MeshStandardMaterial({ color: "#7E8782", transparent: true, opacity: 0.34, roughness: 0.8 }),
  );
  net.position.y = 1.425;
  group.add(net);

  const tape = new THREE.Mesh(
    new THREE.BoxGeometry(20.8, 0.14, 0.18),
    new THREE.MeshStandardMaterial({ color: "#525B56", roughness: 0.8 }),
  );
  tape.position.y = 2.88;
  group.add(tape);

  const postGeometry = new THREE.CylinderGeometry(0.11, 0.11, 3.2, 12);
  const postMaterial = new THREE.MeshStandardMaterial({ color: "#555D59" });
  for (const x of [-10.45, 10.45]) {
    const post = new THREE.Mesh(postGeometry, postMaterial);
    post.position.set(x, 1.6, 0);
    group.add(post);
  }

  return group;
}

interface SolidDashedRun {
  points: THREE.Vector3[];
  dashed: boolean;
}

function splitSolidDashed(trajectory: EstimatedBallTrajectory): SolidDashedRun[] {
  const runs: SolidDashedRun[] = [];
  let current: THREE.Vector3[] = [];
  let currentDashed: boolean | null = null;
  for (const point of trajectory.points) {
    // 未知高度点不渲染（不伪造地面位置），避免制造假落点
    if (point.estimatedHeightFt === null) continue;
    const vec = courtVector(point.courtXFt, point.estimatedHeightFt + 0.08, point.courtYFt);
    const dashed = point.interpolated;
    if (currentDashed !== null && dashed !== currentDashed && current.length >= 2) {
      runs.push({ points: current, dashed: currentDashed });
      current = [];
    }
    current.push(vec);
    currentDashed = dashed;
  }
  if (current.length >= 2) runs.push({ points: current, dashed: currentDashed ?? false });
  return runs;
}

function addTrajectories(
  scene: THREE.Scene,
  trajectories: EstimatedBallTrajectory[],
  selectedShotId: string | null,
): THREE.Line[] {
  const selectableLines: THREE.Line[] = [];
  for (const trajectory of trajectories) {
    const selected = trajectory.shotId !== null && trajectory.shotId === selectedShotId;
    const color = selected ? "#111827" : DIRECTION_COLORS[trajectory.direction];
    const opacity = selected ? 1 : trajectory.highConfidence ? 0.9 : 0.34;

    // 每个飞行段 = 独立 line strip；段内按 source 拆实线 / 虚线，绝不跨事件边界共用样条
    for (const run of splitSolidDashed(trajectory)) {
      const geometry = new THREE.BufferGeometry().setFromPoints(run.points);
      let line: THREE.Line;
      if (run.dashed) {
        const material = new THREE.LineDashedMaterial({
          color,
          transparent: true,
          opacity: opacity * 0.82,
          dashSize: 0.34,
          gapSize: 0.22,
        });
        line = new THREE.Line(geometry, material);
        line.computeLineDistances();
      } else {
        const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
        line = new THREE.Line(geometry, material);
      }
      line.userData.shotId = trajectory.shotId;
      line.userData.trajectoryId = trajectory.id;
      line.renderOrder = selected ? 3 : 2;
      scene.add(line);
      selectableLines.push(line);
    }

    const renderedPoints = trajectory.points
      .filter((point) => point.estimatedHeightFt !== null)
      .map((point) => courtVector(point.courtXFt, point.estimatedHeightFt as number + 0.08, point.courtYFt));
    const endpointMaterial = new THREE.MeshStandardMaterial({ color, transparent: opacity < 1, opacity });
    for (const endpoint of [renderedPoints[0], renderedPoints[renderedPoints.length - 1]]) {
      if (!endpoint) continue;
      const marker = new THREE.Mesh(new THREE.SphereGeometry(selected ? 0.24 : 0.17, 14, 10), endpointMaterial);
      marker.position.copy(endpoint);
      marker.userData.shotId = trajectory.shotId;
      marker.userData.trajectoryId = trajectory.id;
      scene.add(marker);
    }

    // 事件锚点视觉语义：弹地橙色圆环、击球紫色菱形
    for (const anchor of trajectory.anchors ?? []) {
      const vec = courtVector(anchor.courtXFt, 0.08, anchor.courtYFt);
      if (anchor.anchorType === "bounce") {
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(0.22, 0.05, 8, 20),
          new THREE.MeshStandardMaterial({ color: "#F97316", transparent: true, opacity: 0.95 }),
        );
        ring.position.copy(vec);
        ring.rotation.x = Math.PI / 2;
        scene.add(ring);
      } else if (anchor.anchorType === "contact") {
        const diamond = new THREE.Mesh(
          new THREE.OctahedronGeometry(0.2),
          new THREE.MeshStandardMaterial({ color: "#8B5CF6", transparent: true, opacity: 0.95 }),
        );
        diamond.position.copy(vec);
        diamond.scale.y = 1.4;
        scene.add(diamond);
      }
    }
  }
  return selectableLines;
}

function disposeScene(scene: THREE.Scene) {
  scene.traverse((object) => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
    object.geometry.dispose();
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach((material) => material.dispose());
  });
}

export function BallTrajectoryScene({
  trajectories,
  selectedShotId,
  onSelectShot,
  onWebGlError,
}: BallTrajectorySceneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mountRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef<THREE.OrthographicCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const [activeView, setActiveView] = useState<CameraView>("oblique");
  const [isFullscreen, setIsFullscreen] = useState(false);

  const applyView = useCallback((view: CameraView) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    camera.position.set(...VIEW_CONFIG[view].position);
    camera.zoom = view === "side" ? 1.05 : view === "end" ? 1.08 : 1;
    camera.updateProjectionMatrix();
    controls.target.set(0, 1.2, 0);
    controls.update();
    setActiveView(view);
  }, []);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    } catch (error) {
      onWebGlError(error instanceof Error ? error.message : "无法初始化 WebGL");
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor("#F8FAF9", 1);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.domElement.dataset.trajectoryCanvas = "true";
    renderer.domElement.setAttribute("aria-label", "交互式球路球场");
    mount.replaceChildren(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(buildCourt());
    scene.add(new THREE.HemisphereLight("#FFFFFF", "#D7DED9", 2.1));
    const keyLight = new THREE.DirectionalLight("#FFFFFF", 2.3);
    keyLight.position.set(12, 30, 18);
    keyLight.castShadow = true;
    scene.add(keyLight);

    const camera = new THREE.OrthographicCamera(-30, 30, 27.5, -27.5, 0.1, 200);
    cameraRef.current = camera;
    const controls = new OrbitControls(camera, renderer.domElement);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minZoom = 0.7;
    controls.maxZoom = 2.8;
    controls.maxPolarAngle = Math.PI / 2.02;
    controls.target.set(0, 1.2, 0);

    const selectableLines = addTrajectories(scene, trajectories, selectedShotId);

    const resize = () => {
      const width = Math.max(1, mount.clientWidth);
      const height = Math.max(1, mount.clientHeight);
      const frustumHeight = 55;
      const aspect = width / height;
      camera.left = -(frustumHeight * aspect) / 2;
      camera.right = (frustumHeight * aspect) / 2;
      camera.top = frustumHeight / 2;
      camera.bottom = -frustumHeight / 2;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, true);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();
    applyView(activeView);

    const raycaster = new THREE.Raycaster();
    raycaster.params.Line.threshold = 0.42;
    const pointer = new THREE.Vector2();
    const handleClick = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(selectableLines, false)[0];
      // 点击任意飞行段 → 选中整个 Shot（无 shotId 的孤立段按自身选中）
      const shotId = hit?.object.userData.shotId;
      const trajectoryId = hit?.object.userData.trajectoryId;
      if (typeof shotId === "string") onSelectShot(shotId);
      else if (typeof trajectoryId === "string") onSelectShot(trajectoryId);
    };
    renderer.domElement.addEventListener("click", handleClick);

    let animationFrame = 0;
    const render = () => {
      controls.update();
      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(render);
    };
    render();

    const handleContextLost = (event: Event) => {
      event.preventDefault();
      onWebGlError("WebGL context 已丢失，请刷新页面后重试");
    };
    renderer.domElement.addEventListener("webglcontextlost", handleContextLost);

    return () => {
      window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("click", handleClick);
      renderer.domElement.removeEventListener("webglcontextlost", handleContextLost);
      controls.dispose();
      disposeScene(scene);
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, [activeView, applyView, onSelectShot, onWebGlError, selectedShotId, trajectories]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  const toggleFullscreen = async () => {
    const container = containerRef.current;
    if (!container) return;
    if (document.fullscreenElement === container) await document.exitFullscreen();
    else await container.requestFullscreen();
  };

  return (
    <div
      className="relative min-h-[430px] overflow-hidden rounded-lg border border-[#DDE5E0] bg-[#F8FAF9] sm:min-h-[560px] lg:h-[calc(100vh-230px)] lg:min-h-[620px]"
      ref={containerRef}
      data-testid="ball-trajectory-scene"
    >
      <div className="absolute inset-0" ref={mountRef} />
      <div className="absolute right-3 top-3 z-10 flex flex-col gap-2 rounded-lg border border-[#D6DED9] bg-white/92 p-1.5 shadow-sm backdrop-blur-sm sm:right-4 sm:top-4">
        {(Object.keys(VIEW_CONFIG) as CameraView[]).map((view) => {
          const config = VIEW_CONFIG[view];
          const Icon = config.icon;
          return (
            <button
              aria-label={`${config.label}视角`}
              aria-pressed={activeView === view}
              className={`grid size-10 place-items-center rounded-md border transition ${activeView === view ? "border-[#25B86A] bg-[#EAF8F0] text-[#168A34]" : "border-transparent text-[#667085] hover:bg-[#F2F4F3]"}`}
              key={view}
              onClick={() => applyView(view)}
              title={`${config.label}视角`}
              type="button"
            >
              <Icon size={19} aria-hidden="true" />
            </button>
          );
        })}
        <span className="mx-1 h-px bg-[#E4E9E6]" />
        <button
          aria-label={isFullscreen ? "退出全屏" : "全屏查看"}
          className="grid size-10 place-items-center rounded-md text-[#667085] transition hover:bg-[#F2F4F3]"
          onClick={toggleFullscreen}
          title={isFullscreen ? "退出全屏" : "全屏查看"}
          type="button"
        >
          <Expand size={19} aria-hidden="true" />
        </button>
      </div>
      <div className="pointer-events-none absolute bottom-3 left-3 z-10 rounded-md border border-[#D6DED9] bg-white/88 px-3 py-2 text-xs text-[#667085] shadow-sm backdrop-blur-sm sm:bottom-4 sm:left-4">
        拖动旋转 · 滚轮缩放 · 点击球路查看详情
      </div>
    </div>
  );
}
