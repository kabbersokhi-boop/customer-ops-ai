.PHONY: up down seed demo-reset test lint workflows secret-scan verify eval orchestration-eval adversarial-eval providers demo-ready logs clean

up:
	docker compose up -d --build

seed:
	docker compose exec api python scripts/seed_demo.py

demo-reset: up
	docker compose exec -T api python -m scripts.reset_demo --database --airtable --confirm RESET_DEMO

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	PYTHONPATH=. .venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check .

workflows:
	.venv/bin/python scripts/validate_workflows.py

secret-scan:
	.venv/bin/python scripts/secret_scan.py --history

eval:
	.venv/bin/python scripts/run_demo_eval.py

orchestration-eval:
	.venv/bin/python scripts/run_orchestration_eval.py

adversarial-eval:
	.venv/bin/python scripts/run_customer_adversarial_eval.py

providers:
	.venv/bin/python scripts/verify_live_providers.py

demo-ready: up
	python3 scripts/demo_ready.py
	docker compose exec -T api python scripts/verify_live_providers.py

verify: lint workflows secret-scan test

clean:
	docker compose down -v
	rm -f customer_ops.db test_customer_ops.db
