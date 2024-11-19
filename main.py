import requests
from http.client import RemoteDisconnected
import dlt
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources
from dlt.sources.helpers.rest_client.paginators import PageNumberPaginator
from ratelimit import limits, RateLimitException
from itertools import islice
from backoff import on_exception, expo

DEFAULT_API_V3 = 'https://dadosabertos.compras.gov.br'

UASGS = '/modulo-uasg/1_consultarUasg'
LICITACOES = '/modulo-legado/1_consultarLicitacao'
MATERIAL = '/modulo-material/1_consultarGrupoMaterial'
CLASSES = '/modulo-material/2_consultarClasseMaterial'
DESCRIPTIVE = '/modulo-material/3_consultarPdmMaterial'
ITEMS = '/modulo-material/4_consultarItemMaterial'

generators_pipeline = dlt.pipeline(
        pipeline_name="compras_governo",
        destination='duckdb', 
        dataset_name='compras_sc',
        progress="log",
        refresh=True
    )

WAIT_LIMIT = 10

def fetch_json_from_api(module: str, params: dict = {}):

    params['pagina'] = 1

    while True:
        print(DEFAULT_API_V3+module)
        print(params)

        response = requests.get(DEFAULT_API_V3+module, params=params, stream=True)
        response.raise_for_status()
        json_response = response.json()

        yield json_response['resultado']

        if json_response['paginasRestantes'] == 0:     
            break

        params['pagina'] += 1


def fetch_df_municipios():
    import duckdb

    conn = duckdb.connect("./compras_governo.duckdb")
    conn.sql(f"SET search_path = '{generators_pipeline.dataset_name}'")

    return conn.sql("SELECT * FROM municipios__municipios").df()

def fetch_df_uasg():
    import duckdb

    conn = duckdb.connect("./compras_governo.duckdb")
    conn.sql(f"SET search_path = '{generators_pipeline.dataset_name}'")

    return conn.sql("SELECT codigo_uasg as id FROM uasg").df()

def fetch_duckdb_tables():
    import duckdb

    conn = duckdb.connect("./compras_governo.duckdb")
    conn.sql(f"SET search_path = '{generators_pipeline.dataset_name}'")

    return conn.sql("SHOW TABLES").df()

def fetch_max_date_licitacoes(id):
    import duckdb

    conn = duckdb.connect("./compras_governo.duckdb")
    conn.sql(f"SET search_path = '{generators_pipeline.dataset_name}'")

    return conn.sql(f"SELECT max(data_publicacao) as max_date FROM licitacoes WHERE uasg = {id} ").df()

@on_exception(expo, RateLimitException, max_tries=8)
@on_exception(expo, requests.exceptions.Timeout, max_tries=8)
@on_exception(expo, RemoteDisconnected, max_tries=8)
@limits(calls=15, period=WAIT_LIMIT)
def __fetch_usag_licitacoes():

    uasg_df = fetch_df_uasg()
    duck_db_tables = fetch_duckdb_tables()

    tables_name = duck_db_tables['name'].values


    for index, row in uasg_df.iterrows():
        start_date = '1900-01-01'

        if 'licitacoes' in tables_name:
            start_date = fetch_max_date_licitacoes(row['id'])['max_date'].values[0]

        param = {"uasg": row['id'], "data_publicacao_inicial": start_date, "data_publicacao_final": '2025-01-01'}

        info = generators_pipeline.run(generator_data_from_df(row, LICITACOES, param),
            table_name="licitacoes",
            write_disposition="merge",
            primary_key="id_compra",
        )

def generator_data_from_df(row, module: str, params={}):
           
    yield fetch_json_from_api(
        module, 
        params
    )


if __name__ == '__main__':

    info = generators_pipeline.run(fetch_json_from_api(UASGS, {'siglaUf': 'SC', 'statusUasg': True}),
            table_name="uasg",
            write_disposition="merge",
            primary_key="codigoUasg",
        )
    
    info = generators_pipeline.run(fetch_json_from_api(UASGS, {'siglaUf': 'SC', 'statusUasg': False}),
        table_name="uasg",
        write_disposition="merge",
        primary_key="codigoUasg"
    )
    
    __fetch_usag_licitacoes()

    info = generators_pipeline.run(fetch_json_from_api(MATERIAL, {"statusGrupo": True}),
        table_name="material",
        write_disposition="merge",
        primary_key="codigo_grupo",
    )
        

    info = generators_pipeline.run(fetch_json_from_api(MATERIAL, {"statusGrupo": False}),
        table_name="material",
        write_disposition="merge",
        primary_key="codigo_grupo",
    )

    info = generators_pipeline.run(fetch_json_from_api(CLASSES, {"statusClasse": True}),
        table_name="material_classe",
        write_disposition="merge",
        primary_key="codigo_classe",
    )
        

    info = generators_pipeline.run(fetch_json_from_api(CLASSES, {"statusClasse": False}),
        table_name="material_classe",
        write_disposition="merge",
        primary_key="codigo_classe",
    )

    info = generators_pipeline.run(fetch_json_from_api(DESCRIPTIVE, {"statusPdm": False}),
        table_name="material_pdm",
        write_disposition="merge",
        primary_key="codigo_pdm",
    )

    info = generators_pipeline.run(fetch_json_from_api(DESCRIPTIVE, {"statusPdm": True}),
        table_name="material_pdm",
        write_disposition="merge",
        primary_key="codigo_pdm",
    )


    info = generators_pipeline.run(fetch_json_from_api(ITEMS, {"statusItem": False}),
        table_name="material_pdm",
        write_disposition="merge",
        primary_key="codigo_item",
    )

    info = generators_pipeline.run(fetch_json_from_api(ITEMS, {"statusItem": True}),
        table_name="material_pdm",
        write_disposition="merge",
        primary_key="codigo_item",
    )
        
    print("FIM")