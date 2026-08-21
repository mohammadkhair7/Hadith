"""Run the full ETL: migrate schema, load all three sources, run parity checks."""
import time

import migrate
import load_sunna
import load_shamela
import parity

# load_hadith_struct retired 2026-08-20: the hadith_struct page archive is
# reference notes, not a book — removed from the app (ops/remove_alifta_edition.py)


def main() -> None:
    t0 = time.time()
    migrate.main()
    load_sunna.main()
    load_shamela.main()
    parity.main()
    print(f"ETL complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
