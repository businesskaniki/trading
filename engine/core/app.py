from engine.core.dependency import get_settings


def main() -> None:
    settings = get_settings()
    print(f"Athena Quant Engine running in {settings.mode} mode")


if __name__ == "__main__":
    main()
