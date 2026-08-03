import { describe, expect, it } from "vitest";
import { canonicalPlayerNumber, formatPlayerId } from "./analysisHelpers";

describe("canonicalPlayerNumber", () => {
  it("parses Player_1..Player_4 as numbers 1..4", () => {
    expect(canonicalPlayerNumber("Player_1")).toBe(1);
    expect(canonicalPlayerNumber("Player_2")).toBe(2);
    expect(canonicalPlayerNumber("Player_3")).toBe(3);
    expect(canonicalPlayerNumber("Player_4")).toBe(4);
  });

  it("returns null for non-canonical inputs", () => {
    expect(canonicalPlayerNumber(null)).toBeNull();
    expect(canonicalPlayerNumber(undefined)).toBeNull();
    expect(canonicalPlayerNumber("")).toBeNull();
    expect(canonicalPlayerNumber("Player_0")).toBeNull();
    expect(canonicalPlayerNumber("Player_5")).toBeNull();
    expect(canonicalPlayerNumber("164")).toBeNull();
    expect(canonicalPlayerNumber("T164")).toBeNull();
    expect(canonicalPlayerNumber("player_1")).toBeNull();
    expect(canonicalPlayerNumber(" ID 172 ")).toBeNull();
  });

  it("handles leading/trailing whitespace", () => {
    expect(canonicalPlayerNumber("  Player_3  ")).toBe(3);
  });
});

describe("formatPlayerId", () => {
  it("formats canonical player ids as P1..P4", () => {
    expect(formatPlayerId("Player_1")).toBe("P1");
    expect(formatPlayerId("Player_2")).toBe("P2");
    expect(formatPlayerId("Player_3")).toBe("P3");
    expect(formatPlayerId("Player_4")).toBe("P4");
  });

  it("returns empty string for non-canonical values", () => {
    expect(formatPlayerId(null)).toBe("");
    expect(formatPlayerId(undefined)).toBe("");
    expect(formatPlayerId("")).toBe("");
    expect(formatPlayerId("164")).toBe("");
    expect(formatPlayerId("player_1")).toBe("");
  });
});
