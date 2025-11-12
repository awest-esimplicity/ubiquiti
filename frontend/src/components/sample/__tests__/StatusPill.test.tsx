import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPill } from "@/components/sample/StatusPill";

describe("StatusPill", () => {
  it("renders unlocked variant by default", () => {
    render(<StatusPill label="Active device" />);
    const pill = screen.getByText("Active device");
    expect(pill).toBeInTheDocument();
    expect(pill).toHaveAttribute("data-locked", "false");
  });

  it("renders locked variant when specified", () => {
    render(<StatusPill label="Locked device" variant="locked" />);
    const pill = screen.getByText("Locked device");
    expect(pill).toHaveAttribute("data-locked", "true");
    expect(pill.className).toContain("text-status-locked");
  });
});
