"""Long-lived Farasa JAR process wrapper (§12.2): ONE java process per engine,
fed via stdin/stdout — never a per-call subprocess (JVM startup ≈ seconds).

The Grammar folder ships Ant sources without built dists. Build once with:

    cd Grammar/Farasa-Segmenter-Jar && ant jar     (repeat per tool)

Each engine looks for its JAR under <project>/dist/*.jar and reports itself
unavailable (with the build hint) until the JAR exists. The JARs remain the
permanent validation oracles for the Python ports (§12.8)."""
import subprocess
import threading
from pathlib import Path

GRAMMAR_DIR = Path(__file__).resolve().parents[4] / "Grammar"


def find_jar(project: str) -> Path | None:
    dist = GRAMMAR_DIR / project / "dist"
    if dist.exists():
        jars = sorted(dist.glob("*.jar"))
        if jars:
            return jars[0]
    return None


class JarProcess:
    """Line-oriented stdin/stdout bridge to a persistent `java -jar`."""

    def __init__(self, jar: Path, args: list[str] | None = None) -> None:
        self.jar = jar
        self.args = args or []
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            ["java", "-Dfile.encoding=UTF-8", "-jar", str(self.jar), *self.args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=self.jar.parent.parent,           # project root (models resolved relatively)
            encoding="utf-8", errors="replace",
        )

    def process_line(self, line: str) -> str:
        with self._lock:
            self.start()
            assert self._proc and self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(line.replace("\n", " ") + "\n")
            self._proc.stdin.flush()
            return self._proc.stdout.readline().rstrip("\n")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None
