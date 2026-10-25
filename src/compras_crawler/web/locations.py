"""Offline code/state checks shared by imports and the official IBGE lookup."""

UF_CODES = dict(pair.split(":") for pair in (
    "AC:12 AL:27 AP:16 AM:13 BA:29 CE:23 DF:53 ES:32 GO:52 MA:21 MT:51 MS:50 "
    "MG:31 PA:15 PB:25 PR:41 PE:26 PI:22 RJ:33 RN:24 RS:43 RO:11 RR:14 SC:42 SP:35 SE:28 TO:17"
).split())
UFS = set(UF_CODES)


def validate_city_state(code: str, uf: str) -> None:
    if uf not in UF_CODES or not code.startswith(UF_CODES[uf]):
        raise ValueError("o código IBGE não corresponde à UF informada")
