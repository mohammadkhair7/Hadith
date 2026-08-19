"""Run the full ETL: migrate schema, load all three sources, run parity checks."""
import time

import migrate
import load_sunna
import load_shamela
import load_alifta
import parity


def main() -> None:
    t0 = time.time()
    migrate.main()
    load_sunna.main()
    load_shamela.main()
    load_alifta.main()
    parity.main()
    print(f"ETL complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
