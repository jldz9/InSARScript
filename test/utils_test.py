import sys
from pathlib import Path
sys.path.append(Path(__file__).parent.parent.joinpath('src').as_posix())

import unittest


# -------------
# Test tool.py
# -------------
# 1. test tool.get_config function
from insarscript.utils.tool import get_config
class test_tool_get_config(unittest.TestCase):
    def test_no_input(self):
        self.assertTrue(get_config())
    def test_input_not_file(self):
        self.assertRaises(FileNotFoundError, get_config, **{"config_path":'not_exist.yaml'})
    def test_input_wrong_file(self):
        self.assertRaises(ValueError,get_config, **{"config_path":Path(__file__).parents[1].joinpath('environment.yml')})

# -----------
# Test api.py
# -----------
# 1. Test api.fetch_open_meteo_history
from insarscript.utils.apis import get_snow_data
import pandas as pd

class test_api_fetch_open_meteo_history(unittest.TestCase):
    def test_valid_request(self):
        df = get_snow_data()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        
if __name__ == '__main__':
    unittest.main()