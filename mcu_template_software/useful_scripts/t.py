import io
from pyflakes.api import check_path
from pyflakes.reporter import Reporter

stdout = io.StringIO()
stderr = io.StringIO()
reporter = Reporter(stdout, stderr)
check_path("config.py", reporter)
print("STDOUT:", stdout.getvalue())
print("STDERR:", stderr.getvalue())