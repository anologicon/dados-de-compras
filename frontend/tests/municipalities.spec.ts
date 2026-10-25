import { test, expect, type Page } from "@playwright/test";

async function openRegistration(page: Page) {
  await page.goto("/");
  await page
    .locator(".city-selector")
    .getByRole("button", { name: "Cadastrar município", exact: true })
    .click();
  return page.getByRole("dialog", { name: "Cadastrar município" });
}

test("pesquisa IBGE preenche código e cadastra o município oficial", async ({
  page,
}) => {
  const dialog = await openRegistration(page);
  const submit = dialog.getByRole("button", {
    name: "Cadastrar município",
    exact: true,
  });
  await expect(submit).toBeDisabled();
  await dialog
    .getByRole("combobox", { name: "UF", exact: true })
    .selectOption("SC");
  await dialog
    .getByRole("textbox", { name: "Buscar município", exact: true })
    .fill("florianopolis");
  await dialog
    .getByRole("radio", { name: "Florianópolis / SC IBGE 4205407" })
    .check();
  await expect(
    dialog.getByRole("textbox", { name: "Código IBGE", exact: true }),
  ).toHaveValue("4205407");
  await expect(
    dialog.getByRole("textbox", { name: "Código IBGE", exact: true }),
  ).toHaveJSProperty("readOnly", true);
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Município selecionado" }),
  ).toHaveValue("4205407");
});

test("trocar UF invalida a seleção e distingue municípios semelhantes", async ({
  page,
}) => {
  const dialog = await openRegistration(page);
  const uf = dialog.getByRole("combobox", { name: "UF", exact: true });
  const query = dialog.getByRole("textbox", {
    name: "Buscar município",
    exact: true,
  });
  const code = dialog.getByRole("textbox", {
    name: "Código IBGE",
    exact: true,
  });
  await uf.selectOption("SC");
  await query.fill("sao jose");
  await dialog
    .getByRole("radio", { name: "São José / SC IBGE 4216602" })
    .check();
  await expect(code).toHaveValue("4216602");
  await uf.selectOption("SP");
  await expect(code).toHaveValue("");
  await expect(
    dialog.getByRole("button", { name: "Cadastrar município", exact: true }),
  ).toBeDisabled();
  await query.fill("sao jose");
  await expect(dialog.getByRole("radio")).toHaveCount(1);
  await dialog
    .getByRole("radio", { name: "São José dos Campos / SP IBGE 3549904" })
    .check();
  await expect(code).toHaveValue("3549904");
});

test("editar a busca limpa o código e não permite cadastrar resultado anterior", async ({
  page,
}) => {
  const dialog = await openRegistration(page);
  await dialog
    .getByRole("combobox", { name: "UF", exact: true })
    .selectOption("SC");
  const query = dialog.getByRole("textbox", {
    name: "Buscar município",
    exact: true,
  });
  await query.fill("brusque");
  await dialog
    .getByRole("radio", { name: "Brusque / SC IBGE 4202909" })
    .check();
  await query.fill("inexistente");
  await expect(
    dialog.getByRole("textbox", { name: "Código IBGE", exact: true }),
  ).toHaveValue("");
  await expect(
    dialog.getByRole("button", { name: "Cadastrar município", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByText("Nenhum município encontrado nessa UF."),
  ).toBeVisible();
});

test("indisponibilidade sem cache não permite cadastro manual", async ({
  page,
}) => {
  await page.route("**/api/municipalities?**", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "IBGE indisponível e sem catálogo oficial salvo.",
      }),
    }),
  );
  const dialog = await openRegistration(page);
  await dialog
    .getByRole("combobox", { name: "UF", exact: true })
    .selectOption("SC");
  await dialog
    .getByRole("textbox", { name: "Buscar município", exact: true })
    .fill("brusque");
  await expect(dialog.getByRole("alert")).toContainText("IBGE indisponível");
  await expect(
    dialog.getByRole("button", { name: "Cadastrar município", exact: true }),
  ).toBeDisabled();
  await expect(
    dialog.getByRole("textbox", { name: "Código IBGE", exact: true }),
  ).toHaveJSProperty("readOnly", true);
});

test("buscador de município permanece utilizável no celular", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openRegistration(page);
  await dialog
    .getByRole("combobox", { name: "UF", exact: true })
    .selectOption("SC");
  await dialog
    .getByRole("textbox", { name: "Buscar município", exact: true })
    .fill("brusque");
  await dialog
    .getByRole("radio", { name: "Brusque / SC IBGE 4202909" })
    .check();
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  const submit = dialog.getByRole("button", {
    name: "Cadastrar município",
    exact: true,
  });
  await submit.scrollIntoViewIfNeeded();
  await expect(submit).toBeVisible();
  await expect(submit).toBeEnabled();
});

test("catálogo salvo continua selecionável com aviso de indisponibilidade", async ({
  page,
}) => {
  await page.route("**/api/municipalities?**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({
      json: {
        ...data,
        source: "cache",
        warning:
          "Não foi possível atualizar o IBGE; usando o catálogo oficial salvo.",
      },
    });
  });
  const dialog = await openRegistration(page);
  await dialog
    .getByRole("combobox", { name: "UF", exact: true })
    .selectOption("SC");
  await dialog
    .getByRole("textbox", { name: "Buscar município", exact: true })
    .fill("brusque");
  await expect(
    dialog.getByText(
      "Não foi possível atualizar o IBGE; usando o catálogo oficial salvo.",
    ),
  ).toBeVisible();
  await dialog
    .getByRole("radio", { name: "Brusque / SC IBGE 4202909" })
    .check();
  await expect(
    dialog.getByRole("button", { name: "Cadastrar município", exact: true }),
  ).toBeEnabled();
});
