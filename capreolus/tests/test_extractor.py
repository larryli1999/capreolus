from collections import defaultdict

from pymagnitude import Magnitude, MagnitudeUtils
import numpy as np

from capreolus.collection import DummyCollection
from capreolus.index import AnseriniIndex
from capreolus.tokenizer import AnseriniTokenizer
from capreolus.benchmark import DummyBenchmark
from capreolus.extractor import EmbedText
from capreolus.tests.common_fixtures import tmpdir_as_cache, dummy_index

from capreolus.utils.exceptions import MissingDocError
from capreolus.extractor.bagofwords import BagOfWords

MAXQLEN = 8
MAXDOCLEN = 7


def test_embedtext_creation(monkeypatch):
    def fake_magnitude_embedding(*args, **kwargs):
        return Magnitude(None)

    monkeypatch.setattr(EmbedText, "_get_pretrained_emb", fake_magnitude_embedding)

    extractor_cfg = {
        "_name": "embedtext",
        "index": "anserini",
        "tokenizer": "anserini",
        "embeddings": "glove6b",
        "zerounk": True,
        "calcidf": True,
        "maxqlen": MAXQLEN,
        "maxdoclen": MAXDOCLEN,
        "usecache": False,
    }
    extractor = EmbedText(extractor_cfg)

    benchmark = DummyBenchmark({"_fold": "s1", "rundocsonly": False})
    collection = DummyCollection({"_name": "dummy"})

    index_cfg = {"_name": "anserini", "indexstops": False, "stemmer": "porter"}
    index = AnseriniIndex(index_cfg)
    index.modules["collection"] = collection

    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)
    extractor.modules["index"] = index
    extractor.modules["tokenizer"] = tokenizer

    qids = list(benchmark.qrels.keys())  # ["301"]
    qid = qids[0]
    docids = list(benchmark.qrels[qid].keys())
    extractor.create(qids, docids, benchmark.topics[benchmark.query_type])
    expected_vocabs = ["lessdummy", "dummy", "doc", "hello", "greetings", "world", "from", "outer", "space", "<pad>"]
    expected_stoi = {s: i for i, s in enumerate(expected_vocabs)}

    assert set(extractor.stoi.keys()) == set(expected_stoi.keys())

    assert extractor.embeddings.shape == (len(expected_vocabs), 8)
    for i in range(extractor.embeddings.shape[0]):
        if i == extractor.pad:
            assert extractor.embeddings[i].sum() < 1e-5
            continue

    return extractor


def test_embedtext_id2vec(monkeypatch):
    def fake_magnitude_embedding(*args, **kwargs):
        return Magnitude(None)

    monkeypatch.setattr(EmbedText, "_get_pretrained_emb", fake_magnitude_embedding)

    extractor_cfg = {
        "_name": "embedtext",
        "index": "anserini",
        "tokenizer": "anserini",
        "embeddings": "glove6b",
        "zerounk": True,
        "calcidf": True,
        "maxqlen": MAXQLEN,
        "maxdoclen": MAXDOCLEN,
        "usecache": False,
    }
    extractor = EmbedText(extractor_cfg)

    benchmark = DummyBenchmark({"_fold": "s1", "rundocsonly": False})
    collection = DummyCollection({"_name": "dummy"})

    index_cfg = {"_name": "anserini", "indexstops": False, "stemmer": "porter"}
    index = AnseriniIndex(index_cfg)
    index.modules["collection"] = collection

    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)

    extractor.modules["index"] = index
    extractor.modules["tokenizer"] = tokenizer

    qids = list(benchmark.qrels.keys())  # ["301"]
    qid = qids[0]
    docids = list(benchmark.qrels[qid].keys())

    extractor.create(qids, docids, benchmark.topics[benchmark.query_type])

    docid1, docid2 = docids[0], docids[1]
    data = extractor.id2vec(qid, docid1, docid2)
    q, d1, d2, idf = [data[k] for k in ["query", "posdoc", "negdoc", "idfs"]]

    assert q.shape[0] == idf.shape[0]

    topics = benchmark.topics[benchmark.query_type]
    # emb_path = "glove/light/glove.6B.300d"
    # fullemb = Magnitude(MagnitudeUtils.download_model(emb_path))

    assert len(q) == MAXQLEN
    assert len(d1) == MAXDOCLEN
    assert len(d2) == MAXDOCLEN

    assert len([w for w in q if w.sum() != 0]) == len(topics[qid].strip().split()[:MAXQLEN])
    assert len([w for w in d1 if w.sum() != 0]) == len(extractor["index"].get_doc(docid1).strip().split()[:MAXDOCLEN])
    assert len([w for w in d2 if w.sum() != 0]) == len(extractor["index"].get_doc(docid2).strip().split()[:MAXDOCLEN])

    # check MissDocError
    error_thrown = False
    try:
        extractor.id2vec(qid, "0000000", "111111")
    except MissingDocError as err:
        error_thrown = True
        assert err.related_qid == qid
        assert err.missed_docid == "0000000"

    assert error_thrown


def test_embedtext_caching(dummy_index, monkeypatch):
    def fake_magnitude_embedding(*args, **kwargs):
        return Magnitude(None)

    monkeypatch.setattr(EmbedText, "_get_pretrained_emb", fake_magnitude_embedding)

    extractor_cfg = {
        "_name": "embedtext",
        "index": "anserini",
        "tokenizer": "anserini",
        "embeddings": "glove6b",
        "zerounk": True,
        "calcidf": True,
        "maxqlen": MAXQLEN,
        "maxdoclen": MAXDOCLEN,
        "usecache": True,
    }
    extractor = EmbedText(extractor_cfg)

    benchmark = DummyBenchmark({"_fold": "s1", "rundocsonly": False})
    collection = DummyCollection({"_name": "dummy"})

    index_cfg = {"_name": "anserini", "indexstops": False, "stemmer": "porter"}
    index = AnseriniIndex(index_cfg)
    index.modules["collection"] = collection

    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)

    extractor.modules["index"] = index
    extractor.modules["tokenizer"] = tokenizer

    qids = list(benchmark.qrels.keys())  # ["301"]
    qid = qids[0]
    docids = list(benchmark.qrels[qid].keys())

    assert not extractor.is_state_cached(qids, docids)

    extractor.create(qids, docids, benchmark.topics[benchmark.query_type])

    assert extractor.is_state_cached(qids, docids)

    new_extractor = EmbedText(extractor_cfg)

    new_extractor.modules["index"] = index
    new_extractor.modules["tokenizer"] = tokenizer

    assert new_extractor.is_state_cached(qids, docids)
    new_extractor._build_vocab(qids, docids, benchmark.topics[benchmark.query_type])


def test_bagofwords_create(monkeypatch, tmpdir, dummy_index):
    benchmark = DummyBenchmark({})
    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)
    extractor = BagOfWords(
        {"_name": "bagofwords", "datamode": "unigram", "keepstops": True, "maxqlen": 4, "maxdoclen": 800, "usecache": False}
    )
    extractor.modules["index"] = dummy_index
    extractor.modules["tokenizer"] = tokenizer
    extractor.create(["301"], ["LA010189-0001", "LA010189-0002"], benchmark.topics["title"])
    assert extractor.stoi == {
        "<pad>": 0,
        "dummy": 1,
        "doc": 2,
        "hello": 3,
        "world": 4,
        "greetings": 5,
        "from": 6,
        "outer": 7,
        "space": 8,
        "lessdummy": 9,
    }

    assert extractor.itos == {v: k for k, v in extractor.stoi.items()}
    assert extractor.embeddings == {
        "<pad>": 0,
        "dummy": 1,
        "doc": 2,
        "hello": 3,
        "world": 4,
        "greetings": 5,
        "from": 6,
        "outer": 7,
        "space": 8,
        "lessdummy": 9,
    }


def test_bagofwords_create_trigrams(monkeypatch, tmpdir, dummy_index):
    benchmark = DummyBenchmark({})
    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)
    extractor = BagOfWords(
        {"_name": "bagofwords", "datamode": "trigram", "keepstops": True, "maxqlen": 4, "maxdoclen": 800, "usecache": False}
    )
    extractor.modules["index"] = dummy_index
    extractor.modules["tokenizer"] = tokenizer
    extractor.create(["301"], ["LA010189-0001", "LA010189-0002"], benchmark.topics["title"])
    assert extractor.stoi == {
        "<pad>": 0,
        "#du": 1,
        "dum": 2,
        "umm": 3,
        "mmy": 4,
        "my#": 5,
        "#do": 6,
        "doc": 7,
        "oc#": 8,
        "#he": 9,
        "hel": 10,
        "ell": 11,
        "llo": 12,
        "lo#": 13,
        "#wo": 14,
        "wor": 15,
        "orl": 16,
        "rld": 17,
        "ld#": 18,
        "#gr": 19,
        "gre": 20,
        "ree": 21,
        "eet": 22,
        "eti": 23,
        "tin": 24,
        "ing": 25,
        "ngs": 26,
        "gs#": 27,
        "#fr": 28,
        "fro": 29,
        "rom": 30,
        "om#": 31,
        "#ou": 32,
        "out": 33,
        "ute": 34,
        "ter": 35,
        "er#": 36,
        "#sp": 37,
        "spa": 38,
        "pac": 39,
        "ace": 40,
        "ce#": 41,
        "#le": 42,
        "les": 43,
        "ess": 44,
        "ssd": 45,
        "sdu": 46,
    }

    assert extractor.itos == {v: k for k, v in extractor.stoi.items()}


def test_bagofwords_id2vec(tmpdir, dummy_index):
    benchmark = DummyBenchmark({})
    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)
    extractor = BagOfWords(
        {"_name": "bagofwords", "datamode": "unigram", "keepstops": True, "maxqlen": 4, "maxdoclen": 800, "usecache": False}
    )
    extractor.modules["index"] = dummy_index
    extractor.modules["tokenizer"] = tokenizer
    extractor.stoi = {extractor.pad_tok: extractor.pad}
    extractor.itos = {extractor.pad: extractor.pad_tok}
    extractor.idf = defaultdict(lambda: 0)
    # extractor.create(["301"], ["LA010189-0001", "LA010189-0002"], benchmark.topics["title"])

    extractor.qid2toks = {"301": ["dummy", "doc"]}
    extractor.stoi["dummy"] = 1
    extractor.stoi["doc"] = 2
    extractor.itos[1] = "dummy"
    extractor.itos[2] = "doc"
    extractor.docid2toks = {
        "LA010189-0001": ["dummy", "dummy", "dummy", "hello", "world", "greetings", "from", "outer", "space"],
        "LA010189-0002": ["dummy", "dummy", "dummy", "hello", "world", "greetings", "from", "outer", "space"],
    }
    transformed = extractor.id2vec("301", "LA010189-0001", "LA010189-0001")
    # stoi only knows about the word 'dummy' and 'doc'. So the transformation of every other word is set as 0

    assert transformed["qid"] == "301"
    assert transformed["posdocid"] == "LA010189-0001"
    assert transformed["negdocid"] == "LA010189-0001"
    assert np.array_equal(transformed["query"], [0, 1, 1])
    assert np.array_equal(transformed["posdoc"], [6, 3, 0])
    assert np.array_equal(transformed["negdoc"], [6, 3, 0])
    assert np.array_equal(transformed["query_idf"], [0, 0, 0])


def test_bagofwords_id2vec_trigram(tmpdir, dummy_index):
    benchmark = DummyBenchmark({})
    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)
    extractor = BagOfWords(
        {"_name": "bagofwords", "datamode": "trigram", "keepstops": True, "maxqlen": 4, "maxdoclen": 800, "usecache": False}
    )
    extractor.modules["index"] = dummy_index
    extractor.modules["tokenizer"] = tokenizer
    extractor.stoi = {extractor.pad_tok: extractor.pad}
    extractor.itos = {extractor.pad: extractor.pad_tok}
    extractor.idf = defaultdict(lambda: 0)
    # extractor.create(["301"], ["LA010189-0001", "LA010189-0002"], benchmark.topics["title"])

    extractor.qid2toks = {"301": ["dummy", "doc"]}
    extractor.docid2toks = {
        "LA010189-0001": ["dummy", "dummy", "dummy", "hello", "world", "greetings", "from", "outer", "space"],
        "LA010189-0002": ["dummy", "dummy", "dummy", "hello", "world", "greetings", "from", "outer", "space"],
    }
    extractor.stoi["#du"] = 1
    extractor.stoi["dum"] = 2
    extractor.stoi["umm"] = 3
    extractor.itos[1] = "#du"
    extractor.itos[2] = "dum"
    extractor.itos[3] = "umm"
    transformed = extractor.id2vec("301", "LA010189-0001")

    # stoi only knows about the word 'dummy'. So the transformation of every other word is set as 0
    assert transformed["qid"] == "301"
    assert transformed["posdocid"] == "LA010189-0001"
    assert transformed.get("negdocid") is None

    # Right now we have only 3 words in the vocabular - "<pad>", "dummy" and "doc"
    assert np.array_equal(transformed["query"], [5, 1, 1, 1])
    assert np.array_equal(
        transformed["posdoc"], [39, 3, 3, 3]
    )  # There  are 6 unknown words in the doc, so all of them is encoded as 0
    assert np.array_equal(transformed["query_idf"], [0, 0, 0, 0])

    # Learn another word
    extractor.stoi["mmy"] = 4
    extractor.stoi["my#"] = 5
    extractor.stoi["#he"] = 6
    extractor.itos[4] = "mmy"
    extractor.itos[5] = "my#"
    extractor.itos[6] = "#he"

    transformed = extractor.id2vec("301", "LA010189-0001")
    # The posdoc transformation changes to reflect the new word
    assert np.array_equal(transformed["posdoc"], [32, 3, 3, 3, 3, 3, 1])


def test_bagofwords_caching(dummy_index, monkeypatch):
    def fake_magnitude_embedding(*args, **kwargs):
        return Magnitude(None)

    monkeypatch.setattr(EmbedText, "_get_pretrained_emb", fake_magnitude_embedding)

    extractor_cfg = {
        "_name": "bagofwords",
        "datamode": "trigram",
        "keepstops": True,
        "maxqlen": 4,
        "maxdoclen": 800,
        "usecache": True,
    }
    extractor = BagOfWords(extractor_cfg)

    benchmark = DummyBenchmark({"_fold": "s1", "rundocsonly": False})
    collection = DummyCollection({"_name": "dummy"})

    index_cfg = {"_name": "anserini", "indexstops": False, "stemmer": "porter"}
    index = AnseriniIndex(index_cfg)
    index.modules["collection"] = collection

    tok_cfg = {"_name": "anserini", "keepstops": True, "stemmer": "none"}
    tokenizer = AnseriniTokenizer(tok_cfg)

    extractor.modules["index"] = index
    extractor.modules["tokenizer"] = tokenizer

    qids = list(benchmark.qrels.keys())  # ["301"]
    qid = qids[0]
    docids = list(benchmark.qrels[qid].keys())

    assert not extractor.is_state_cached(qids, docids)

    extractor.create(qids, docids, benchmark.topics[benchmark.query_type])

    assert extractor.is_state_cached(qids, docids)

    new_extractor = EmbedText(extractor_cfg)

    new_extractor.modules["index"] = index
    new_extractor.modules["tokenizer"] = tokenizer

    assert new_extractor.is_state_cached(qids, docids)
    new_extractor._build_vocab(qids, docids, benchmark.topics[benchmark.query_type])