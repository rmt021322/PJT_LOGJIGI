"""Catch mismatches between the current template and the script's element IDs.

This doesn't execute JavaScript or inspect browser layout; it protects the
HTML/JS connection that broke when connectError was removed.
"""
import re
import unittest
from pathlib import Path
from collections import Counter
from bs4 import BeautifulSoup
from app import app

ROOT=Path(__file__).resolve().parents[1]

class UIContractTests(unittest.TestCase):
    def test_script_element_ids_exist_once_in_rendered_screen(self):
        html=app.test_client().get('/').data.decode('utf-8')
        elements=Counter(node['id'] for node in BeautifulSoup(html,'html.parser').select('[id]'))
        script=(ROOT/'static/script.js').read_text(encoding='utf-8')
        referenced=set(re.findall(r"\$\('([a-zA-Z0-9_-]+)'\)",script))
        for name in sorted(referenced):
            with self.subTest(element_id=name):
                self.assertEqual(elements[name],1,f'JavaScript가 사용하는 #{name} 영역이 화면에 정확히 한 개 있어야 합니다.')

if __name__=='__main__':unittest.main()
