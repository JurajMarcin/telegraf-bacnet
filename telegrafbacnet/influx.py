from multiprocessing import Process, Queue
from time import time_ns
from typing import Any


class InfluxLine:
    def __init__(self, key: str, value: Any, *tags: tuple[str, Any]) -> None:
        self.key = key
        self.value = value
        self.tags = tags
        self.timestamp = time_ns()


class InfluxLPR:
    def __init__(self) -> None:
        self.queue: Queue[InfluxLine] = Queue()
        self.print_job = Process(target=self._print_task)
        self.print_job.start()

    def print(self, key: str, value: Any, *tags: tuple[str, Any]) -> None:
        self.queue.put(InfluxLine(key, value, *tags))

    def _print_task(self):
        try:
            while True:
                line = self.queue.get(block=True)
                self._print_influx_line(line)
        except KeyboardInterrupt:
            pass

    @staticmethod
    def _print_influx_line(line: InfluxLine) -> None:
        tags_str = ",".join(f"{tagKey}={tagValue}"
                            for tagKey, tagValue in line.tags)
        tags_str = f",{tags_str}" if tags_str else tags_str
        value = line.value
        if isinstance(value, list):
            for index, inner in enumerate(value):
                print(f"bacnet{tags_str},index={index} "
                      f"{line.key}={inner} {line.timestamp}")
        else:
            print(f"bacnet{tags_str} {line.key}={line.value} {line.timestamp}")
