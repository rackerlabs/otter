pep8=pep8
pep257=pep257

lint:
	${pep8} otter/
	${pep257} otter/*