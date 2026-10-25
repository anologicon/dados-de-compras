import { test, expect } from "@playwright/test";

test("panorama, filtros, origem e exportação", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Visão geral." }),
  ).toBeVisible();
  await expect(
    page.getByText("Cobertura não verificada", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "1",
  );
  await page
    .getByRole("textbox", { name: "Buscar compras" })
    .fill("inexistente");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "0",
  );
  await page.getByRole("button", { name: "Limpar", exact: true }).click();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "1",
  );
  await page.getByRole("button", { name: "Compras", exact: true }).click();
  await page
    .getByRole("button", {
      name: "Aquisição de material hospitalar",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toContainText("teste-001");
  await page
    .getByRole("button", { name: "Rastreabilidade", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("pncp_test");
  await page.keyboard.press("Escape");
  const exported = await request.get("/api/cities/4202909/export?format=json");
  expect((await exported.json()).records[0].original.idCompra).toBe(
    "teste-001",
  );
  await page
    .getByRole("button", { name: "Dados de origem", exact: true })
    .click();
  await expect(page.locator(".raw-item").first()).toContainText(
    "Aquisição de material hospitalar",
  );
  expect(errors).toEqual([]);
});

test("fila de coletas e agenda persistente", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Nova coleta", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Adicionar à fila", exact: true })
    .click();
  await expect(
    page.getByText("Na fila", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Parar coleta", exact: true })
    .first()
    .click();
  await expect(page.getByText("Parada", { exact: true }).first()).toBeVisible();
  await page
    .getByRole("button", { name: "Retomar coleta", exact: true })
    .first()
    .click();
  await expect(
    page.getByText("Na fila", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Agendas", exact: true }).click();
  await page.getByRole("button", { name: "Nova agenda", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Nome da rotina", exact: true })
    .fill("Rotina de teste");
  await page.getByRole("button", { name: "Criar agenda", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Rotina de teste" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Pausar agenda", exact: true })
    .click();
  await expect(
    page.getByText("Pausada", { exact: true }).first(),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Agendas", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Rotina de teste" }),
  ).toBeVisible();
});

test("layout móvel não causa rolagem horizontal da página", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "1",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
