import { expect, test } from "@playwright/test";

test.describe("Home dashboard", () => {
  test("displays owner cards and opens pin modal", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h2", { hasText: "Owners" })).toBeVisible();
    const ownerCard = page.getByRole("button", { name: /house/i });
    await ownerCard.click();
    await expect(page.getByText("Enter the 4-digit PIN")).toBeVisible();
  });
});
