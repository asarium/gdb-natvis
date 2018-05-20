from typing import Dict


class TypeManager:
    type_map: Dict[str, str]

    def __init__(self) -> None:
        super().__init__()

        self.type_map = {}

    def get_type_string(self, type):
        pass
