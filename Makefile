TARGET ?= dev

.PHONY: install lint fmt test eval build validate deploy etl app grant agent-eval all

install:        ## create .venv with runtime + dev deps
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest --cov=retail_insights --cov-report=term-missing

eval:           ## offline agent eval, same as CI
	uv run retail-eval --offline

build:
	uv build --wheel

validate:
	databricks bundle validate -t $(TARGET)

deploy:
	databricks bundle deploy -t $(TARGET)

etl:
	databricks bundle run retail_etl -t $(TARGET)

grant:
	uv run retail-grant-app --app-name retail-insights-$(TARGET) --catalog workspace --schema retail_$(TARGET)

app:
	databricks bundle run retail_app -t $(TARGET)

agent-eval:
	databricks bundle run retail_agent_eval -t $(TARGET)

all: lint test eval deploy etl grant app   ## everything, end to end
