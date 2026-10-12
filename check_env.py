"""Phase 1 environment check. Run with: python check_env.py"""
import sys


def main() -> None:
    ok = True

    # 1. Python version
    version = sys.version_info
    print(f"Python version : {version.major}.{version.minor}.{version.micro}")
    if (version.major, version.minor) < (3, 10):
        print("  [FAIL] Python 3.10+ required")
        ok = False

    # 2. Are we inside the virtual environment?
    in_venv = sys.prefix != sys.base_prefix
    print(f"Interpreter    : {sys.executable}")
    print(f"Inside venv    : {in_venv}")
    if not in_venv:
        print("  [FAIL] Activate the venv: .\\.venv\\Scripts\\Activate.ps1")
        ok = False

    # 3. Django installed?
    try:
        import django
        print(f"Django version : {django.get_version()}")
    except ImportError:
        print('  [FAIL] Django not installed: pip install "Django>=5.2,<5.3"')
        ok = False

    # 4. python-dotenv installed?
    try:
        import dotenv  # noqa: F401
        print("python-dotenv  : installed")
    except ImportError:
        print("  [FAIL] python-dotenv not installed: pip install python-dotenv")
        ok = False

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()