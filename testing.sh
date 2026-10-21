unzip BioMCP_v0.2_upgrade.zip
cd BioMCP
ls -la
#drwxr-xr-x@ 11 yuqizhao  staff   352 Oct 21 13:42 .
#drwxr-xr-x  13 yuqizhao  staff   416 Oct 21 13:41 ..
#-rw-r--r--@  1 yuqizhao  staff  1498 Oct 16 12:47 ADR_V2.md
#-rw-r--r--@  1 yuqizhao  staff  2013 Oct 16 12:47 app.py
#-rw-r--r--@  1 yuqizhao  staff   211 Oct 16 12:47 generate_password_hash.py
#-rw-r--r--@  1 yuqizhao  staff  1041 Oct 16 12:47 pyproject.toml
#-rw-r--r--@  1 yuqizhao  staff  3065 Oct 16 12:47 README_V2.md
#-rw-r--r--@  1 yuqizhao  staff  3597 Oct 16 12:46 README.md
#drwxr-xr-x@  3 yuqizhao  staff    96 May  1 20:51 src
#-rw-r--r--   1 yuqizhao  staff    41 Oct 21 13:42 testing.sh
#drwxr-xr-x@  5 yuqizhao  staff   160 Oct 16 12:47 tests
python3 -m venv .venv
source .venv/bin/activate
python --version
#Python 3.13.12
# Upgrade the packaging tools:
python -m pip install --upgrade pip setuptools wheel
# This installs BioMCP in editable mode with tools such as pytest, pytest-asyncio, respx, and ruff.
python -m pip install -e ".[dev]"
python -m pip show ensembl-uniprot-mcp
python -m pip check
python -c "import mcp, gradio, httpx, bcrypt, pydantic; print('Dependencies OK')"
python -c "from ensembl_uniprot_mcp.research import ResearchService; print('BioMCP import OK')"
# Install compatible MCP 1.x
python -m pip install --upgrade "mcp>=1.0,<2.0"
python -m ruff check .                   
#All checks passed!
python -m compileall -q app.py src tests
python generate_password_hash.py
#biomcptesting
export BIOMCP_USER="yuqizhao"
read -r -s "BIOMCP_PASSWORD_HASH?Paste bcrypt hash: "
echo
export BIOMCP_PASSWORD_HASH

