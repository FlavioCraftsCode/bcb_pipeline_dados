import pytest

from bcb_pipeline.status import StatusExecucao, StatusSerie, status_da_execucao

OK, QUAR, INT = StatusSerie.SUCESSO, StatusSerie.QUARENTENA, StatusSerie.INTERROMPIDA


@pytest.mark.parametrize(
    ("por_serie", "erro", "esperado"),
    [
        ({"432": OK, "433": OK}, None, StatusExecucao.SUCESSO),
        ({"432": OK, "433": QUAR}, None, StatusExecucao.CONCLUIDO_COM_ISOLAMENTO),
        ({"432": QUAR, "433": QUAR}, None, StatusExecucao.CONCLUIDO_COM_ISOLAMENTO),
        ({"432": OK, "433": INT}, None, StatusExecucao.CONCLUIDO_COM_ISOLAMENTO),
        ({"432": INT, "433": INT}, None, StatusExecucao.INTERROMPIDA),
        ({"432": OK}, "OperationalError: conexão perdida", StatusExecucao.INTERROMPIDA),
        ({}, None, StatusExecucao.INTERROMPIDA),
    ],
)
def test_status_da_execucao(por_serie, erro, esperado):
    assert status_da_execucao(por_serie, erro) is esperado


def test_vocabulario_nao_usa_termos_antigos():
    valores = {v.value for enum in (StatusExecucao, StatusSerie) for v in enum}
    assert not valores & {"falha", "parcial", "alerta"}


def test_schemas_da_api_rejeitam_vocabulario_antigo():
    pydantic = pytest.importorskip("pydantic")
    from bcb_api.schemas import ResultadoQualidade

    base = {"codigo_bcb": "432", "checagem": "faixa_valida", "detalhe": "x"}
    assert ResultadoQualidade(**base, status="bloqueante").status.value == "bloqueante"
    with pytest.raises(pydantic.ValidationError):
        ResultadoQualidade(**base, status="falha")
