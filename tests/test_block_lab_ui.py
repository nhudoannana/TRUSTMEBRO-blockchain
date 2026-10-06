"""Block cards are now part of the single chain workspace."""
import pytest

from tests.test_blockchain_lab_ui import run_chain_case


@pytest.mark.parametrize('case', ['cards', 'headers', 'safe_text', 'repeated',
                                  'edit_first', 'draft', 'max_blocks'])
def test_combined_block_cards(case):
    run_chain_case(case)
