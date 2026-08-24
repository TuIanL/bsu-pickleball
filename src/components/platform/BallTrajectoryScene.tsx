import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Columns3, Expand, Focus, Rows3 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import type { EstimatedBallTrajectory, EstimatedTrajectoryPoint } from "../../services/ballTrajectoryVisualization";

export type CameraView = "oblique" | "top" | "sideline" | "baseline" | "obliqueBaseline";

interface BallTrajectorySceneProps {
  trajectories: EstimatedBallTrajectory[];
  selectedShotId: string | null;
  onSelectShot: (shotId: string | null) => void;
  onWebGlError: (message: string) => void;
}

interface ViewConfig {
  position: [number, number, number];
  label: string;
  icon: LucideIcon;
  zoom: number;
}

export const VIEW_CONFIG: Record<CameraView, ViewConfig> = {
  oblique: { position: [30, 28, 36], label: "45°", icon: Box, zoom: 1 },
  top: { position: [0.01, 55, 0.01], label: "俯视", icon: Rows3, zoom: 1 },
  sideline: { position: [40, 12, 0], label: "边线", icon: Columns3, zoom: 1.05 },
  baseline: { position: [0, 14, 44], label: "底线", icon: Focus, zoom: 1.08 },
  obliqueBaseline: { position: [-30, 26, 38], label: "45°底线", icon: Box, zoom: 1.02 },
};

const DIRECTION_COLORS = {
  "near-to-far": "#25B86A",
  "far-to-near": "#F04438",
} as const;

const MAX_RENDER_GAP_SECONDS = 0.55;
const VIEWPORT_BACKGROUND = "#F5F8F6";

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
    new THREE.MeshStandardMaterial({ color: "#E5EBE7", roughness: 0.92, metalness: 0 }),
  );
  surface.rotation.x = -Math.PI / 2;
  surface.receiveShadow = true;
  group.add(surface);

  const boundaryMaterial = new THREE.LineBasicMaterial({ color: "#59645E" });
  const innerMaterial = new THREE.LineBasicMaterial({ color: "#8A958E" });
  addCourtLine(group, [[-10, -22], [10, -22], [10, 22], [-10, 22], [-10, -22]], boundaryMaterial);
  addCourtLine(group, [[-10, -7], [10, -7]], innerMaterial);
  addCourtLine(group, [[-10, 7], [10, 7]], innerMaterial);
  addCourtLine(group, [[0, -22], [0, -7]], innerMaterial);
  addCourtLine(group, [[0, 7], [0, 22]], innerMaterial);

  const kitchenMaterial = new THREE.MeshStandardMaterial({ color: "#D3DCD6", transparent: true, opacity: 0.62 });
  const kitchenNear = new THREE.Mesh(new THREE.PlaneGeometry(20, 7), kitchenMaterial);
  kitchenNear.rotation.x = -Math.PI / 2;
  kitchenNear.position.set(0, 0.012, -10.5);
  group.add(kitchenNear);
  const kitchenFar = kitchenNear.clone();
  kitchenFar.position.z = 10.5;
  group.add(kitchenFar);

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

export interface SolidDashedRun {
  points: THREE.Vector3[];
  style: "detected" | "interpolated" | "predicted";
}

function pointStyle(point: EstimatedTrajectoryPoint): SolidDashedRun["style"] {
  return point.source === "model_predicted"
    ? "predicted"
    : point.source === "interpolated"
      ? "interpolated"
      : "detected";
}

function isRenderablePoint(point: EstimatedTrajectoryPoint): boolean {
  return Number.isFinite(point.courtXFt) && Number.isFinite(point.courtYFt) && point.estimatedHeightFt !== null;
}

function isGap(previous: EstimatedTrajectoryPoint | null, current: EstimatedTrajectoryPoint): boolean {
  return previous !== null && current.timestampSeconds - previous.timestampSeconds > MAX_RENDER_GAP_SECONDS;
}

export function getLastRenderablePoint(trajectory: EstimatedBallTrajectory): EstimatedTrajectoryPoint | null {
  return [...trajectory.points].reverse().find(isRenderablePoint) ?? null;
}

/**
 * 将 source 样式切换做成重叠 run，避免 source 切换处生成孤立单点短线。
 * 无效高度和长时间缺失会清空当前 run，保证不跨真实丢失边界连线。
 */
export function splitTrajectoryRuns(trajectory: EstimatedBallTrajectory): SolidDashedRun[] {
  const runs: SolidDashedRun[] = [];
  let current: THREE.Vector3[] = [];
  let currentStyle: SolidDashedRun["style"] | null = null;
  let previous: EstimatedTrajectoryPoint | null = null;

  const flush = () => {
    if (current.length >= 2 && currentStyle) runs.push({ points: current, style: currentStyle });
    current = [];
    currentStyle = null;
  };

  for (const point of trajectory.points) {
    if (!isRenderablePoint(point)) {
      flush();
      previous = null;
      continue;
    }
    if (isGap(previous, point)) {
      flush();
      previous = null;
    }

    const vec = courtVector(point.courtXFt, point.estimatedHeightFt as number + 0.08, point.courtYFt);
    const style = pointStyle(point);
    if (currentStyle === null) {
      current = [vec];
      currentStyle = style;
    } else if (style !== currentStyle) {
      const boundary = current[current.length - 1];
      if (current.length >= 2) runs.push({ points: current, style: currentStyle });
      current = boundary ? [boundary, vec] : [vec];
      currentStyle = style;
    } else {
      current.push(vec);
    }
    previous = point;
  }
  flush();
  return runs;
}

/** 只按真实无效/长丢失边界拆分，source 切换保持几何连续。 */
export function splitContinuousTrajectoryPaths(trajectory: EstimatedBallTrajectory): THREE.Vector3[][] {
  const paths: THREE.Vector3[][] = [];
  let current: THREE.Vector3[] = [];
  let previous: EstimatedTrajectoryPoint | null = null;

  const flush = () => {
    if (current.length >= 2) paths.push(current);
    current = [];
  };

  for (const point of trajectory.points) {
    if (!isRenderablePoint(point)) {
      flush();
      previous = null;
      continue;
    }
    if (isGap(previous, point)) {
      flush();
      previous = null;
    }
    current.push(courtVector(point.courtXFt, point.estimatedHeightFt as number + 0.08, point.courtYFt));
    previous = point;
  }
  flush();
  return paths;
}

interface TrajectoryRenderObjects {
  objects: THREE.Object3D[];
  selectableLines: THREE.Object3D[];
  lineMaterials: LineMaterial[];
}

function createTrajectoryLine(
  points: THREE.Vector3[],
  color: string,
  opacity: number,
  selected: boolean,
  style: SolidDashedRun["style"],
): { line: Line2; material: LineMaterial } {
  const geometry = new LineGeometry();
  geometry.setPositions(points.flatMap((point) => [point.x, point.y, point.z]));
  const material = new LineMaterial({
    color,
    dashed: style !== "detected",
    dashSize: style === "predicted" ? 0.5 : 0.72,
    gapSize: style === "predicted" ? 0.36 : 0.18,
    linewidth: selected ? 3.6 : 2.5,
    opacity,
    transparent: true,
    depthTest: false,
  });
  material.resolution.set(1, 1);
  const line = new Line2(geometry, material);
  line.computeLineDistances();
  return { line, material };
}

function addTrajectories(
  scene: THREE.Scene,
  trajectories: EstimatedBallTrajectory[],
  selectedShotId: string | null,
): TrajectoryRenderObjects {
  const objects: THREE.Object3D[] = [];
  const selectableLines: THREE.Object3D[] = [];
  const lineMaterials: LineMaterial[] = [];

  for (const trajectory of trajectories) {
    const selected = trajectory.shotId !== null && trajectory.shotId === selectedShotId;
    const color = DIRECTION_COLORS[trajectory.direction];
    const opacity = selected ? 1 : trajectory.highConfidence ? 0.94 : 0.46;

    // 基线只在真实缺失处断开；覆盖线表达 source，不会把切换点拆成单点线段。
    for (const path of splitContinuousTrajectoryPaths(trajectory)) {
      const base = createTrajectoryLine(path, color, opacity * 0.84, selected, "detected");
      base.line.userData.shotId = trajectory.shotId;
      base.line.userData.trajectoryId = trajectory.id;
      base.line.renderOrder = selected ? 3 : 2;
      scene.add(base.line);
      objects.push(base.line);
      selectableLines.push(base.line);
      lineMaterials.push(base.material);
    }

    for (const run of splitTrajectoryRuns(trajectory)) {
      if (run.style === "detected") continue;
      const overlay = createTrajectoryLine(
        run.points,
        color,
        opacity * (run.style === "predicted" ? 0.48 : 0.68),
        selected,
        run.style,
      );
      overlay.line.userData.shotId = trajectory.shotId;
      overlay.line.userData.trajectoryId = trajectory.id;
      overlay.line.renderOrder = selected ? 4 : 3;
      scene.add(overlay.line);
      objects.push(overlay.line);
      selectableLines.push(overlay.line);
      lineMaterials.push(overlay.material);
    }

    const lastPoint = getLastRenderablePoint(trajectory);
    if (lastPoint) {
      const terminal = new THREE.Mesh(
        new THREE.SphereGeometry(selected ? 0.25 : 0.19, 14, 10),
        new THREE.MeshStandardMaterial({
          color: selected ? "#344054" : "#667085",
          roughness: 0.7,
          transparent: true,
          opacity: selected ? 1 : 0.86,
        }),
      );
      terminal.position.copy(courtVector(lastPoint.courtXFt, lastPoint.estimatedHeightFt as number + 0.08, lastPoint.courtYFt));
      terminal.userData.shotId = trajectory.shotId;
      terminal.userData.trajectoryId = trajectory.id;
      terminal.renderOrder = 5;
      scene.add(terminal);
      objects.push(terminal);
    }
  }
  return { objects, selectableLines, lineMaterials };
}

function disposeObject(object: THREE.Object3D) {
  const disposable = object as THREE.Object3D & {
    geometry?: THREE.BufferGeometry;
    material?: THREE.Material | THREE.Material[];
  };
  disposable.geometry?.dispose();
  const materials = disposable.material
    ? Array.isArray(disposable.material) ? disposable.material : [disposable.material]
    : [];
  materials.forEach((material) => material.dispose());
}

function disposeScene(scene: THREE.Scene) {
  scene.traverse((object) => disposeObject(object));
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
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const trajectoryObjectsRef = useRef<THREE.Object3D[]>([]);
  const selectableLinesRef = useRef<THREE.Object3D[]>([]);
  const lineMaterialsRef = useRef<LineMaterial[]>([]);
  const activeViewRef = useRef<CameraView>("oblique");
  const onSelectShotRef = useRef(onSelectShot);
  const [activeView, setActiveView] = useState<CameraView>("oblique");
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    onSelectShotRef.current = onSelectShot;
  }, [onSelectShot]);

  const applyView = useCallback((view: CameraView) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    camera.position.set(...VIEW_CONFIG[view].position);
    camera.zoom = VIEW_CONFIG[view].zoom;
    camera.updateProjectionMatrix();
    controls.target.set(0, 1.2, 0);
    controls.update();
  }, []);

  const selectView = useCallback((view: CameraView) => {
    activeViewRef.current = view;
    setActiveView(view);
    applyView(view);
  }, [applyView]);

  const updateTrajectoryObjects = useCallback(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    trajectoryObjectsRef.current.forEach((object) => {
      scene.remove(object);
      disposeObject(object);
    });
    const rendered = addTrajectories(scene, trajectories, selectedShotId);
    trajectoryObjectsRef.current = rendered.objects;
    selectableLinesRef.current = rendered.selectableLines;
    lineMaterialsRef.current = rendered.lineMaterials;
  }, [selectedShotId, trajectories]);

  useEffect(() => {
    updateTrajectoryObjects();
  }, [updateTrajectoryObjects]);

  // Three.js 初始化只执行一次；轨迹、选中态和视角分别由独立 effect 更新。
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
    renderer.setClearColor(VIEWPORT_BACKGROUND, 1);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.domElement.dataset.trajectoryCanvas = "true";
    renderer.domElement.setAttribute("aria-label", "交互式球路球场");
    mount.replaceChildren(renderer.domElement);
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    sceneRef.current = scene;
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
    applyView(activeViewRef.current);

    const initialRendered = addTrajectories(scene, trajectories, selectedShotId);
    trajectoryObjectsRef.current = initialRendered.objects;
    selectableLinesRef.current = initialRendered.selectableLines;
    lineMaterialsRef.current = initialRendered.lineMaterials;

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
      lineMaterialsRef.current.forEach((material) => material.resolution.set(width, height));
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();

    const raycaster = new THREE.Raycaster();
    raycaster.params.Line.threshold = 0.42;
    const pointer = new THREE.Vector2();
    const handleClick = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(selectableLinesRef.current, false)[0];
      const shotId = hit?.object.userData.shotId;
      const trajectoryId = hit?.object.userData.trajectoryId;
      if (typeof shotId === "string") onSelectShotRef.current(shotId);
      else if (typeof trajectoryId === "string") onSelectShotRef.current(trajectoryId);
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
      trajectoryObjectsRef.current = [];
      selectableLinesRef.current = [];
      lineMaterialsRef.current = [];
      sceneRef.current = null;
      rendererRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, [applyView, onWebGlError]);

  useEffect(() => {
    applyView(activeView);
  }, [activeView, applyView]);

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
      className="relative min-h-[430px] overflow-hidden rounded-lg bg-[#F5F8F6] sm:min-h-[560px] lg:h-[calc(100vh-230px)] lg:min-h-[620px]"
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
              data-active={activeView === view ? "true" : "false"}
              key={view}
              onClick={() => selectView(view)}
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
