import { test, expect, type Page } from "@playwright/test";

async function openPurchase(page: Page) {
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Compras", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "Aquisição de material hospitalar",
      exact: true,
    })
    .click();
  return page.getByRole("dialog", { name: "Detalhes da compra" });
}

test("ficha distingue valor selecionado e originais das duas fontes", async ({ page }) => {
  await page.route("**/purchase-detail?*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.conciliation = {
      selected_source: "pncp_direct",
      observations: [
        { source: "pncp_direct", entity: "pncp_direct_contratacao", selected: true,
          payload_json: '{"objeto":"original-direto"}', origin_json: '{"job":"direto"}' },
        { source: "comprasgov", entity: "pncp_contratacao", selected: false,
          payload_json: '{"objeto":"original-comprasgov"}', origin_json: '{"job":"gov"}' },
      ],
      divergences: { estimated: { pncp_direct: 0, comprasgov: 50 } },
    };
    await route.fulfill({ response, json: body });
  });
  const dialog = await openPurchase(page);
  await expect(dialog.getByText("Valores selecionados: PNCP direto.")).toBeVisible();
  await dialog.getByRole("button", { name: "Registro original", exact: true }).click();
  const alternative = dialog.getByText("Compras.gov.br · pncp_contratacao", { exact: true });
  await alternative.click();
  await expect(dialog.getByText(/original-comprasgov/)).toBeVisible();
});

test("compra → item → resultado → fornecedor preserva contexto, fontes e CPF mascarado", async ({
  page,
}) => {
  const errors: string[] = [];
  const mutations: string[] = [];
  const external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.method() !== "GET") mutations.push(request.url());
    if (new URL(request.url()).hostname !== "127.0.0.1") external.push(request.url());
  });
  const dialog = await openPurchase(page);
  await expect(
    dialog.getByRole("button", { name: "Itens (25)", exact: true }),
  ).toBeEnabled();
  await expect(dialog.locator(".relationship-metrics")).toContainText(
    "24itens com compra confirmada",
  );
  await dialog
    .getByRole("button", { name: "Explorar itens", exact: true })
    .click();
  await expect(dialog.locator(".connected-card")).toHaveCount(20);
  const item = dialog.locator(".connected-card").first();
  await expect(item).toContainText("Luva hospitalar");
  await expect(item.locator("dd").filter({ hasText: /^0$/ })).toHaveCount(1);
  await item.getByText("Ver registro e proveniência", { exact: true }).click();
  await expect(item.locator(".source-record")).toContainText("teste-item-1");
  await expect(item.locator(".source-record")).toContainText(
    "pncp_item_contratacao",
  );
  await dialog
    .getByRole("button", { name: "Ver resultados do item 1", exact: true })
    .click();
  await expect(dialog.locator(".item-context")).toContainText(
    "Luva hospitalar",
  );
  await expect(dialog.locator(".result-card")).toHaveCount(20);
  await expect(dialog.locator(".result-card").first()).toContainText(
    /R\$\s*0,00/,
  );
  await dialog
    .getByRole("button", { name: "Ver fornecedor", exact: true })
    .first()
    .click();
  const profile = dialog.getByRole("region", { name: "Perfil do fornecedor" });
  await expect(profile).toContainText("Cadastro vinculado");
  await expect(profile).toContainText("Fornecedor hospitalar de teste");
  await expect(profile).toContainText(
    "Nome no cadastro: Fornecedor no cadastro local",
  );
  await expect(profile).toContainText("12.345.678/0001-99");
  await profile
    .getByRole("button", { name: "Voltar aos resultados", exact: true })
    .click();
  await expect(dialog.locator(".item-context")).toContainText(
    "Luva hospitalar",
  );
  await dialog
    .getByRole("button", { name: "Próxima página", exact: true })
    .click();
  await expect(dialog.locator(".result-card")).toHaveCount(3);
  const person = dialog
    .locator(".result-card")
    .filter({ hasText: "Pessoa de teste" });
  await expect(person).toContainText("Cancelado");
  expect(await person.innerText()).toContain("***.***.***-90");
  expect(await person.innerText()).not.toContain("01234567890");
  await person
    .getByRole("button", { name: "Ver fornecedor", exact: true })
    .click();
  await expect(profile).toContainText("Pessoa no cadastro local");
  expect(await profile.innerText()).not.toContain("01234567890");
  await profile
    .getByRole("button", { name: "Voltar aos resultados", exact: true })
    .click();
  await expect(dialog.locator(".pagination")).toContainText("Página 2");
  await expect(dialog.locator(".result-card")).toHaveCount(3);
  expect(errors).toEqual([]);
  expect(mutations).toEqual([]);
  expect(external).toEqual([]);
});

test("vínculos ambíguos e resultados sem item são explícitos e não forçam associação", async ({
  page,
}) => {
  const dialog = await openPurchase(page);
  await dialog.getByRole("button", { name: "Itens (25)", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Próxima página", exact: true })
    .click();
  const ambiguousItem = dialog
    .locator(".connected-card")
    .filter({ hasText: "Item com identificadores conflitantes" });
  await expect(ambiguousItem).toContainText("Ambíguo");
  await expect(ambiguousItem).toContainText("controle PNCP divergente");
  await expect(
    ambiguousItem.getByRole("button", {
      name: "Ver resultados do item 25",
      exact: true,
    }),
  ).toBeDisabled();
  await dialog
    .getByRole("button", { name: "Resultados (26)", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Próxima página", exact: true })
    .click();
  const contradictory = dialog
    .locator(".result-card")
    .filter({ hasText: "RESULTADO 24" });
  await expect(contradictory).toContainText("Ambíguo");
  await expect(
    contradictory.getByRole("button", { name: "Ver fornecedor", exact: true }),
  ).toHaveCount(0);
  await expect(contradictory).toContainText("Não fazemos associação por nome");
  const orphan = dialog.locator(".result-card").filter({ hasText: "ITEM 99" });
  await expect(orphan.locator(".relation.missing")).toContainText(
    "Não encontrado",
  );
  await expect(orphan.locator(".relation.confirmed")).toContainText(
    "Vínculo com a compra",
  );
});

test("fornecedor identificado pode não ter cadastro no snapshot", async ({
  page,
}) => {
  const dialog = await openPurchase(page);
  await dialog.getByRole("button", { name: "Itens (25)", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Ver resultados do item 2", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Ver fornecedor", exact: true })
    .click();
  const profile = dialog.getByRole("region", { name: "Perfil do fornecedor" });
  await expect(profile).toContainText("Sem cadastro neste snapshot");
  await expect(profile).toContainText("Fornecedor sem cadastro");
  await expect(profile.locator(".registration-card")).toHaveCount(0);
  await expect(profile).not.toContainText("Cadastro vinculado");
});

test("backend anterior mantém resumo e JSON utilizáveis sem tela branca", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/cities/*/purchase-detail?**", (route) =>
    route.fulfill({ status: 404, json: { detail: "Not Found" } }),
  );
  const dialog = await openPurchase(page);
  await expect(dialog).toContainText(
    "Explorador indisponível nesta versão do serviço",
  );
  await expect(dialog).toContainText("Aquisição de material hospitalar");
  await expect(
    dialog.getByRole("button", { name: "Itens", exact: true }),
  ).toBeDisabled();
  await dialog
    .getByRole("button", { name: "Registro original", exact: true })
    .click();
  await expect(dialog.locator(".json")).toContainText("teste-001");
  await dialog
    .getByRole("button", { name: "Rastreabilidade", exact: true })
    .click();
  await expect(dialog.locator(".json")).toContainText("pncp_test");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Compras.", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("mudança de snapshot interrompe a navegação e permite atualizar a ficha", async ({
  page,
}) => {
  await page.route("**/api/cities/*/purchase-items?**", (route) =>
    route.fulfill({
      status: 409,
      json: {
        detail:
          "O snapshot mudou. Atualize a ficha para não misturar versões dos dados.",
      },
    }),
  );
  const dialog = await openPurchase(page);
  await dialog.getByRole("button", { name: "Itens (25)", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("O snapshot mudou");
  await expect(dialog.locator(".connected-card")).toHaveCount(0);
  await page.unroute("**/api/cities/*/purchase-items?**");
  await dialog
    .getByRole("button", { name: "Atualizar ficha", exact: true })
    .click();
  await dialog.getByRole("button", { name: "Itens (25)", exact: true }).click();
  await expect(dialog.locator(".connected-card")).toHaveCount(20);
});

test("ficha conectada cabe no celular e fecha sem bloquear a aplicação", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openPurchase(page);
  await dialog.getByRole("button", { name: "Itens (25)", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Ver resultados do item 1", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Ver fornecedor", exact: true })
    .first()
    .click();
  await expect(dialog).toContainText("Cadastro vinculado");
  expect(
    await dialog.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("combobox", { name: "Município selecionado" })
    .selectOption("4216602");
  await expect(page.locator("tbody tr")).toHaveCount(20);
  await page.locator(".object-link").first().click();
  const nextDialog = page.getByRole("dialog", { name: "Detalhes da compra" });
  await nextDialog
    .getByRole("button", { name: "Itens (0)", exact: true })
    .click();
  await expect(nextDialog).toContainText(
    "Nenhum item vinculado neste snapshot",
  );
  await expect(nextDialog).not.toContainText("Luva hospitalar");
});
