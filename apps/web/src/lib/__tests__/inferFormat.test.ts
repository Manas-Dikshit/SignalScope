import { describe, it, expect } from "vitest";
import { inferFormatFromFilename, type FileFormat } from "@/lib/utils";

describe("inferFormatFromFilename", () => {
  const cases: [string, FileFormat][] = [
    ["capture.wav", "wav"],
    ["signal.WAV", "wav"],
    ["recording.iq", "raw_iq"],
    ["recording.bin", "raw_iq"],
    ["recording.dat", "raw_iq"],
    ["recording.raw", "raw_iq"],
    ["header.sigmf-meta", "sigmf"],
    ["payload.sigmf-data", "sigmf"],
    ["metadata.json", "sigmf"],
    ["no_extension", "raw_iq"],
    ["weird.name.txt", "raw_iq"],
  ];

  it.each(cases)("maps %s to %s", (filename, expected) => {
    expect(inferFormatFromFilename(filename)).toBe(expected);
  });
});
