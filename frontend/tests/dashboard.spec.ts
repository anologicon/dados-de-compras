import { test, expect, type Page } from "@playwright/test";
import type { Overview } from "../src/api";

async function openRichOverview(page: Page) {
  await page.goto("/");
  await page
    .getByRole("combobox", { name: "Município selecionado" })
    .selectOption("4216602");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "20",
  );
}

const navigation = (page: Page) =>
  page.getByRole("navigation", { name: "Navegação principal" });

test("evolução alterna medidas, preserva ausências e oferece valores exatos", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openRichOverview(page);
  await expect(page.locator(".bar-column")).toHaveCount(12);
  const controls = page.getByRole("group", {
    name: "Medida da evolução mensal",
  });
  await controls.getByRole("button", { name: "Estimado", exact: true }).click();
  await expect(
    controls.getByRole("button", { name: "Estimado", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const missing = page.getByRole("button", {
    name: /março.*2026: Não informado/,
  });
  await missing.focus();
  await expect(missing.locator(".missing-mark")).toHaveText("n/d");
  await expect(page.locator(".chart-readout")).toContainText("março de 2026");
  await expect(page.locator(".chart-readout")).toContainText("Não informado");
  const zero = page.getByRole("button", { name: /janeiro.*2026: R\$\s*0,00/ });
  await expect(zero.locator(".zero-mark")).toHaveCount(1);
  await expect(zero.locator(".missing-mark")).toHaveCount(0);
  await controls
    .getByRole("button", { name: "Homologado", exact: true })
    .click();
  await expect(
    page
      .getByRole("button", { name: /dezembro.*2025: R\$\s*0,00/ })
      .locator(".zero-mark"),
  ).toHaveCount(1);
  await page
    .getByText("Ver dados mensais e valores exatos", { exact: true })
    .click();
  await expect(page.locator(".chart-data tbody tr")).toHaveCount(12);
  await expect(page.locator(".chart-data table")).toContainText("900.000,00");
  await expect(
    page.getByRole("meter", { name: "Valor estimado", exact: true }),
  ).toHaveAttribute("aria-valuenow", "18");
  await expect(
    page.getByRole("meter", { name: "Valor homologado", exact: true }),
  ).toHaveAttribute("aria-valuenow", "14");
  await expect(page.locator(".modality-list")).toContainText(
    "Outras modalidades",
  );
  expect(errors).toEqual([]);
});

test("ranking por valor encontra órgão fora do top por volume e abre o recorte exportável", async ({
  page,
  request,
}) => {
  await openRichOverview(page);
  await expect(page.locator(".org-row")).toHaveCount(6);
  await expect(page.locator(".org-row").first()).not.toContainText(
    "Z - Órgão de maior valor",
  );
  await page
    .getByRole("combobox", { name: "Ordenar órgãos por" })
    .selectOption("awarded");
  await expect(page.locator(".org-row").first()).toContainText(
    "Z - Órgão de maior valor",
  );
  await page.locator(".org-row").first().click();
  await expect(
    page.getByRole("heading", { name: "Compras.", exact: true }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator(".filter-summary")).toContainText(
    "Z - Órgão de maior valor",
  );
  const url = await page
    .getByRole("link", { name: "JSON", exact: true })
    .getAttribute("href");
  const response = await request.get(url!);
  const exported = await response.json();
  expect(exported.records).toHaveLength(1);
  expect(exported.metadata.filters.org_name).toBe("Z - Órgão de maior valor");
  await navigation(page)
    .getByRole("button", { name: "Visão geral", exact: true })
    .click();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "1",
  );
  await page.getByRole("button", { name: /Remover filtro de órgão:/ }).click();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "20",
  );
  await page.locator(".modality-list button").first().click();
  await expect(page.locator("tbody tr")).toHaveCount(4);
  await expect(page.locator(".filter-summary")).toContainText("Modalidade 1");
});

test("recorte vazio e falha não se apresentam como valores financeiros zero", async ({
  page,
}) => {
  await openRichOverview(page);
  await page.getByLabel("Publicação inicial").fill("2026-03-01");
  await page.getByLabel("Publicação final").fill("2026-03-31");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "2",
  );
  await page
    .getByRole("group", { name: "Medida da evolução mensal" })
    .getByRole("button", { name: "Estimado", exact: true })
    .click();
  await expect(page.locator(".missing-mark")).toHaveCount(1);
  await expect(page.locator(".chart-axis span")).toHaveText(["—", "—", "—"]);
  await page.getByRole("button", { name: "Limpar", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Buscar compras" })
    .fill("sem resultado algum");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "0",
  );
  await expect(page.locator(".metric").nth(1).locator("strong")).toHaveText(
    "Não informado",
  );
  await expect(page.locator(".metric").nth(2).locator("strong")).toHaveText(
    "Não informado",
  );
  await expect(page.locator(".quality-row").first()).toContainText("—");
  await expect(page.locator(".bar-column")).toHaveCount(0);
  await expect(
    page.getByText("Cobertura não verificada", { exact: true }),
  ).toBeVisible();
  await page.route("**/api/cities/*/overview?**", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Projeção temporariamente indisponível" },
    }),
  );
  await page.getByRole("button", { name: "Limpar", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Projeção temporariamente indisponível",
  );
  await expect(page.locator(".metrics")).toHaveCount(0);
});

test("frontend novo funciona com backend anterior sem inventar dados nem bloquear navegação", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let previousApi = true;
  await page.route("**/api/cities/*/overview?**", async (route) => {
    const response = await route.fetch();
    if (!previousApi) return route.fulfill({ response });
    const data: Overview = await response.json();
    // This is the real pre-revamp response contract, including its volume-only
    // top-eight organizations and absent per-month completeness counts.
    const { organization_known, modality_known, ...metrics } = data.metrics;
    await route.fulfill({
      json: {
        metrics,
        monthly: data.monthly.map(
          ({ estimated_known, awarded_known, ...row }) => row,
        ),
        organizations: data.organizations
          .sort((a, b) => b.purchases - a.purchases)
          .slice(0, 8)
          .map(({ org_name, purchases, awarded }) => ({
            org_name,
            purchases,
            awarded,
          })),
        modalities: data.modalities,
        orgs: data.orgs,
        coverage: data.coverage,
        date_range: data.date_range,
      },
    });
  });
  await openRichOverview(page);
  await expect(
    page.getByText("Serviço em versão anterior", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".bar-column")).toHaveCount(12);
  await expect(page.locator(".quality-panel")).toHaveCount(0);
  await expect(page.locator(".modality-panel")).toHaveCount(0);
  await expect(
    page.getByRole("combobox", { name: "Ordenar órgãos por" }),
  ).toHaveCount(0);
  await page
    .getByRole("group", { name: "Medida da evolução mensal" })
    .getByRole("button", { name: "Estimado", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /março.*2026: Não informado/ }),
  ).toHaveAttribute("aria-label", /preenchimento mensal indisponível/);
  await page
    .getByText("Ver dados mensais e valores exatos", { exact: true })
    .click();
  await expect(page.locator(".chart-data table")).toContainText(
    "Indisponível nesta versão",
  );
  await expect(page.locator(".chart-data table")).not.toContainText(
    "undefined",
  );
  await navigation(page)
    .getByRole("button", { name: "Compras", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(20);
  await navigation(page)
    .getByRole("button", { name: "Dados de origem", exact: true })
    .click();
  await expect(page.locator(".raw-item").first()).toBeVisible();
  await navigation(page)
    .getByRole("button", { name: "Visão geral", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Buscar compras" })
    .fill("nenhum resultado");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "0",
  );
  await expect(page.locator(".metric").nth(1).locator("strong")).toHaveText(
    "Não informado",
  );
  previousApi = false;
  await page.getByRole("button", { name: "Limpar", exact: true }).click();
  await expect(page.locator(".modality-panel")).toBeVisible();
  await expect(page.locator(".quality-panel")).toBeVisible();
  await expect(
    page.getByText("Serviço em versão anterior", { exact: true }),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("panorama completo cabe no celular e em telas médias com rolagem interna nos gráficos", async ({
  page,
}) => {
  for (const width of [390, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await openRichOverview(page);
    for (const value of await page.locator(".metric > strong").all()) {
      expect(
        await value.evaluate((element) => {
          const range = document.createRange();
          range.selectNodeContents(element);
          return range.getClientRects().length;
        }),
      ).toBe(1);
    }
    await page
      .getByText("Ver dados mensais e valores exatos", { exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("heading", {
        name: "O que os registros informam",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      navigation(page).getByRole("button", { name: "Compras", exact: true }),
    ).toBeVisible();
  }
});
