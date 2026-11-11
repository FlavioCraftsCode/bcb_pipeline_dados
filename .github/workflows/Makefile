.PHONY: instalar subir etl etl-completo api painel painel-dev testes testes-integracao lint formatar

instalar:
	pip install -r requirements-dev.txt
	cd frontend && npm install

subir:
	docker compose up -d postgres_dw

etl:
	PYTHONPATH=src python -m bcb_pipeline executar

etl-completo:
	PYTHONPATH=src python -m bcb_pipeline executar --completo

api:
	uvicorn bcb_api.main:app --reload --app-dir src

painel:
	cd frontend && npm run build

painel-dev:
	cd frontend && npm run dev

testes:
	pytest -m "not integracao" --cov=bcb_pipeline --cov-report=term-missing

testes-integracao:
	pytest -m integracao

lint:
	ruff check src tests
	ruff format --check src tests
	cd frontend && npm run typecheck

formatar:
	ruff check --fix src tests
	ruff format src tests
