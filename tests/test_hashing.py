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


class TestZoteroMetadataHash:
    def test_golden_value_stable(self):
        data = {'title': 'Test', 'authors': ['B', 'A'], 'tags': ['z', 'a'],
                'abstract': 'abs', 'date': '2020'}
        assert hashing.compute_zotero_metadata_hash(data) == \
            "7ae38fa1ffcd0320dbe8eab5aa9d9166"

    def test_author_and_tag_order_irrelevant(self):
        a = {'authors': ['B', 'A'], 'tags': ['y', 'x']}
        b = {'authors': ['A', 'B'], 'tags': ['x', 'y']}
        assert hashing.compute_zotero_metadata_hash(a) == \
            hashing.compute_zotero_metadata_hash(b)

    def test_none_authors_tags_safe(self):
        assert hashing.compute_zotero_metadata_hash({}) == \
            hashing.compute_zotero_metadata_hash({'authors': None, 'tags': None})

    def test_matches_watchdog_zotero(self):  # Invariante I1 (Zotero)
        from src.archilles.watchdog import _compute_zotero_metadata_hash
        data = {'title': 'T', 'authors': ['A', 'B'], 'tags': ['a', 'b'],
                'abstract': 'x', 'date': '2021'}
        assert hashing.compute_zotero_metadata_hash(data) == \
            _compute_zotero_metadata_hash(data)


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
