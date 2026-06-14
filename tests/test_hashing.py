"""Befund 7.15: kanonische Hash-Funktionen, byte-identisch zu den Altpfaden."""
from src.archilles import hashing


class TestMetadataHash:
    def test_golden_value_stable(self):
        # Friert den exakten Hash ein: jede Aenderung an der Logik faellt hier auf.
        meta = {
            'title': 'Sein und Zeit', 'author': 'Heidegger, Martin',
            'tags': ['Philosophie', 'Ontologie'], 'comments': 'Hauptwerk.',
            'publisher': 'Niemeyer',
        }
        assert hashing.compute_metadata_hash(meta) == \
            "9c36a5c80b1f266850dd5e199417db96"

    def test_empty_meta_is_empty_string(self):
        assert hashing.compute_metadata_hash({}) == ''
        assert hashing.compute_metadata_hash(None) == ''

    def test_tag_order_irrelevant(self):
        a = {'tags': ['b', 'a', 'c']}
        b = {'tags': ['c', 'b', 'a']}
        assert hashing.compute_metadata_hash(a) == hashing.compute_metadata_hash(b)

    def test_list_and_comma_string_equal(self):  # Invariante I3
        as_list = {'tags': ['Geschichte', 'Politik']}
        as_str = {'tags': 'Politik,Geschichte'}
        assert hashing.compute_metadata_hash(as_list) == \
            hashing.compute_metadata_hash(as_str)


class TestAnnotationHash:
    def test_golden_value_stable(self):
        annots = [
            {'highlighted_text': 'A', 'notes': 'n1', 'type': 'highlight'},
            {'highlighted_text': 'B', 'notes': '', 'type': 'note'},
        ]
        assert hashing.compute_annotation_hash(annots) == \
            "7e4682d750c1403031d766230fa6df5c"

    def test_empty_is_empty_string(self):
        assert hashing.compute_annotation_hash([]) == ''

    def test_order_irrelevant(self):
        a = [{'highlighted_text': 'X'}, {'highlighted_text': 'Y'}]
        b = [{'highlighted_text': 'Y'}, {'highlighted_text': 'X'}]
        assert hashing.compute_annotation_hash(a) == hashing.compute_annotation_hash(b)


class TestEquivalenceWithLegacyPaths:
    """Byte-Identitaet gegen jede bestehende Kopie (Invarianten I1/I2)."""

    META = {
        'title': 'Test', 'author': 'A & B',
        'tags': ['z', 'a'], 'comments': 'c', 'publisher': 'p',
    }
    ANNOTS = [{'highlighted_text': 'h', 'notes': 'n', 'type': 'highlight'}]

    def test_matches_watchdog(self):
        from src.archilles.watchdog import _compute_metadata_hash
        assert hashing.compute_metadata_hash(self.META) == _compute_metadata_hash(self.META)

    def test_matches_engine_static(self):
        from src.archilles.engine import ArchillesRAG
        assert hashing.compute_metadata_hash(self.META) == \
            ArchillesRAG._compute_metadata_hash(self.META)
        assert hashing.compute_annotation_hash(self.ANNOTS) == \
            ArchillesRAG._compute_annotation_hash(self.ANNOTS)

    def test_matches_patch_comments(self):
        from scripts.patch_comments import _compute_metadata_hash as pc_hash
        assert hashing.compute_metadata_hash(self.META) == pc_hash(self.META)
