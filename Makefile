# Helper variables
PACKAGE_NAME = policybench

install:
	pip install -e .[dev]

test:
	pytest --maxfail=1 --disable-warnings -q

format:
	black $(PACKAGE_NAME) tests

lint:
	flake8 $(PACKAGE_NAME) tests

benchmark:
	python -m $(PACKAGE_NAME).main
	# or: policybench
