PYTHON = python
PIP = pip

init:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) tests/test_all.py

test0:
	$(PYTHON) tests/test_all.py --only 0
test1:
	$(PYTHON) tests/test_all.py --only 1
test2:
	$(PYTHON) tests/test_all.py --only 2
test3:
	$(PYTHON) tests/test_all.py --only 3
test4:
	$(PYTHON) tests/test_all.py --only 4
test5:
	$(PYTHON) tests/test_all.py --only 5
test6:
	$(PYTHON) tests/test_all.py --only 6
test7:
	$(PYTHON) tests/test_all.py --only 7
test8:
	$(PYTHON) tests/test_all.py --only 8
test9:
	$(PYTHON) tests/test_all.py --only 9
test10:
	$(PYTHON) tests/test_all.py --only 10