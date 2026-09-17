"""Corpus access and the input validation in front of the ingestion pipeline."""
import unicodedata
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import caches
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from curriculum.ocr_ingest import (CHAPTER_NAMES, DEFAULT_CHAPTER, MIN_PAGE_CHARS,
                                   chapter_spans, chapter_start, is_thin)
from curriculum.rag_engine import RAGEngine, tokenize


def enrol(username, role='STUDENT'):
    user = User.objects.create_user(username=username, password='Testpass!2345')
    ParticipantProfile.objects.create(user=user, role=role, consent_given=True)
    return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)


class CorpusAccessTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        _, self.student = enrol('stu')
        _, self.teacher = enrol('tea', role='EXPERT_TEACHER')
        _, self.boss = enrol('boss', role='RESEARCHER_ADMIN')
        self.anon = APIClient()

    def test_the_textbook_corpus_is_not_public(self):
        self.assertIn(self.anon.get('/api/curriculum/passages/').status_code, (401, 403))
        self.assertIn(self.anon.post('/api/curriculum/search/', {'query': 'loop'},
                                     format='json').status_code, (401, 403))

    def test_participants_cannot_dump_the_corpus(self):
        self.assertEqual(self.student.get('/api/curriculum/passages/').status_code, 403)
        self.assertEqual(self.student.post('/api/curriculum/search/', {'query': 'loop'},
                                           format='json').status_code, 403)

    def test_staff_can_inspect_the_corpus(self):
        self.assertEqual(self.teacher.get('/api/curriculum/passages/').status_code, 200)
        self.assertEqual(self.teacher.post('/api/curriculum/search/', {'query': 'loop'},
                                           format='json').status_code, 200)

    def test_index_status_is_available_to_any_participant(self):
        """The student dashboard shows whether the curriculum index is ready."""
        self.assertEqual(self.student.get('/api/curriculum/status/').status_code, 200)
        self.assertIn(self.anon.get('/api/curriculum/status/').status_code, (401, 403))


class IngestionGuardTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        _, self.student = enrol('stu')
        _, self.teacher = enrol('tea', role='EXPERT_TEACHER')
        _, self.boss = enrol('boss', role='RESEARCHER_ADMIN')

    def test_only_a_researcher_can_start_an_ingestion_run(self):
        """A full pass is hours of billed vision-model calls."""
        with patch('curriculum.views.start_background_ingest', return_value=True) as start:
            self.assertEqual(self.student.post('/api/curriculum/ingest/', {}, format='json').status_code, 403)
            self.assertEqual(self.teacher.post('/api/curriculum/ingest/', {}, format='json').status_code, 403)
            start.assert_not_called()
            self.assertEqual(self.boss.post('/api/curriculum/ingest/', {}, format='json').status_code, 200)
            start.assert_called_once()

    def test_a_malformed_page_range_is_rejected_rather_than_crashing(self):
        """`lo, hi = str(pages).split('-')` used to raise ValueError and return a 500."""
        with patch('curriculum.views.start_background_ingest', return_value=True) as start:
            for bad in ('abc', '140', '1-2-3', '-', 'x-y'):
                # Ingestion is rate limited to 5/hour, so clear the throttle history
                # between cases: this test is about validation, not about the limit.
                caches['default'].clear()
                response = self.boss.post('/api/curriculum/ingest/', {'pages': bad}, format='json')
                self.assertEqual(response.status_code, 400, bad)
            start.assert_not_called()

    def test_an_absent_page_range_means_the_whole_document(self):
        with patch('curriculum.views.start_background_ingest', return_value=True) as start:
            self.assertEqual(self.boss.post('/api/curriculum/ingest/', {}, format='json').status_code, 200)
            self.assertIsNone(start.call_args.kwargs['page_range'])

    def test_the_ingest_rate_limit_actually_bites(self):
        with patch('curriculum.views.start_background_ingest', return_value=True):
            codes = [self.boss.post('/api/curriculum/ingest/', {}, format='json').status_code
                     for _ in range(7)]
        self.assertIn(429, codes, 'a full OCR pass must not be startable without limit')

    def test_a_reversed_page_range_is_rejected(self):
        with patch('curriculum.views.start_background_ingest', return_value=True):
            self.assertEqual(
                self.boss.post('/api/curriculum/ingest/', {'pages': '170-140'}, format='json').status_code,
                400)

    def test_a_valid_page_range_is_passed_through(self):
        with patch('curriculum.views.start_background_ingest', return_value=True) as start:
            self.boss.post('/api/curriculum/ingest/', {'pages': '140-170'}, format='json')
            self.assertEqual(start.call_args.kwargs['page_range'], (140, 170))

    def test_the_worker_count_is_clamped(self):
        with patch('curriculum.views.start_background_ingest', return_value=True) as start:
            self.boss.post('/api/curriculum/ingest/', {'workers': 500}, format='json')
            self.assertLessEqual(start.call_args.kwargs['workers'], 8)
            self.boss.post('/api/curriculum/ingest/', {'workers': 'lots'}, format='json')
            self.assertEqual(start.call_args.kwargs['workers'], 3)


class SearchInputTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        _, self.teacher = enrol('tea', role='EXPERT_TEACHER')

    def test_a_non_numeric_k_falls_back_instead_of_raising(self):
        response = self.teacher.post('/api/curriculum/search/',
                                     {'query': 'loop', 'k': 'not-a-number'}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_k_is_bounded_so_one_query_cannot_ask_for_the_whole_corpus(self):
        with patch('curriculum.views.rag_engine_instance.search_passages',
                   return_value=[]) as search:
            self.teacher.post('/api/curriculum/search/', {'query': 'loop', 'k': 100000},
                              format='json')
            self.assertLessEqual(search.call_args.kwargs['k'], 50)
            self.teacher.post('/api/curriculum/search/', {'query': 'loop', 'k': -5}, format='json')
            self.assertGreaterEqual(search.call_args.kwargs['k'], 1)

    def test_an_empty_query_returns_no_passages(self):
        response = self.teacher.post('/api/curriculum/search/', {'query': ''}, format='json')
        self.assertEqual(response.json()['results_count'], 0)


class TokenizerTests(ApiTestCase):
    def test_english_and_bangla_words_are_both_tokenised(self):
        self.assertIn('loop', tokenize('The loop runs'))
        self.assertTrue(any('ঀ' <= ch <= '৿' for ch in ''.join(tokenize('লুপ চলে'))))

    def test_single_characters_and_punctuation_are_dropped(self):
        self.assertEqual(tokenize('a b cd!'), ['cd'])

    def test_tokenising_is_case_insensitive(self):
        self.assertEqual(tokenize('LOOP Loop'), ['loop', 'loop'])

    def test_empty_input_is_safe(self):
        self.assertEqual(tokenize(''), [])
        self.assertEqual(tokenize(None), [])


class KeywordRetrievalTests(ApiTestCase):
    """With no vector index the engine must still return grounded-looking passages."""

    def test_retrieval_falls_back_to_seed_passages_and_says_so(self):
        engine = RAGEngine()
        with patch.object(engine, 'vector_count', return_value=0):
            results = engine.retrieve('loop control structures', k=3)
        self.assertTrue(results)
        self.assertEqual(engine.last_backend, 'keyword')
        self.assertIn('Seed passage', results[0]['source_ref'])

    def test_an_empty_query_retrieves_nothing(self):
        engine = RAGEngine()
        self.assertEqual(engine.retrieve('', k=3), [])
        self.assertEqual(engine.retrieve('   ', k=3), [])

    def test_a_language_filter_is_respected(self):
        engine = RAGEngine()
        with patch.object(engine, 'vector_count', return_value=0):
            results = engine.retrieve('loop', k=5, language='en')
        self.assertTrue(all(r['language'] == 'en' for r in results))


class ChapterStructureTests(ApiTestCase):
    """Which chapter a passage is filed under decides what the tutor can retrieve for a task, so the
    labels have to come from the structure of the book rather than from whatever a page mentions."""

    HTML_OPENER = 'চতুর্থ অধ্যায়\n\nওয়েব ডিজাইন পরিচিতি এবং HTML\nIntroduction to Web Design and HTML'
    C_OPENER = 'পঞ্চম অধ্যায়\n\nপ্রোগ্রামিং ভাষা\nProgramming Language'
    DB_OPENER = '**ষষ্ঠ অধ্যায়**\n\n**ডেটাবেজ ম্যানেজমেন্ট সিস্টেম**\n**Database Management System**'
    # Page 122 of the Bangla textbook: body prose that names another chapter's title in passing.
    PROSE_NAMING_C = ('এই কাজের জন্য সবচেয়ে জনপ্রিয় প্রোগ্রামিং ভাষা হচ্ছে জাভাস্ক্রিপ্ট (Javascript)। '
                      'একটি ওয়েবসাইটে এক বা একাধিক ওয়েব পেজ থাকে।')

    def test_prose_naming_another_chapter_does_not_reopen_it(self):
        spans = chapter_spans({1: self.HTML_OPENER, 2: self.PROSE_NAMING_C, 3: 'HTML এলিমেন্ট'})
        self.assertEqual(spans[2], CHAPTER_NAMES[4])
        self.assertEqual(spans[3], CHAPTER_NAMES[4])

    def test_a_chapter_runs_until_the_next_one_opens(self):
        spans = chapter_spans({
            1: 'front matter', 2: self.HTML_OPENER, 3: 'tags', 4: self.C_OPENER, 5: 'loops',
            6: self.DB_OPENER, 7: 'SQL SELECT',
        })
        self.assertEqual([spans[p] for p in (2, 3)], [CHAPTER_NAMES[4]] * 2)
        self.assertEqual([spans[p] for p in (4, 5)], [CHAPTER_NAMES[5]] * 2)
        self.assertEqual([spans[p] for p in (6, 7)], [CHAPTER_NAMES[6]] * 2)
        self.assertEqual(spans[1], DEFAULT_CHAPTER)

    def test_both_bangla_normalisations_of_a_heading_are_recognised(self):
        """The model writes 'য়' either precomposed (U+09DF) or as য plus a nukta, and page 119 of
        the real cache uses the precomposed form while this file's literal does not. U+09DF is a
        composition exclusion, so NFC settles both on the decomposed pair; matching raw strings
        against only one of the two is what lost chapters 4 to 6."""
        precomposed = self.HTML_OPENER.replace('য়', 'য়')
        self.assertNotEqual(precomposed, self.HTML_OPENER)
        self.assertEqual(unicodedata.normalize('NFC', precomposed),
                         unicodedata.normalize('NFC', self.HTML_OPENER))
        self.assertEqual(chapter_start(precomposed), 4)
        self.assertEqual(chapter_start(self.HTML_OPENER), 4)

    def test_a_backward_cross_reference_cannot_rewind_the_book(self):
        spans = chapter_spans({1: self.DB_OPENER, 2: 'প্রথম অধ্যায়', 3: 'more SQL'})
        self.assertEqual(spans[3], CHAPTER_NAMES[6])

    def test_an_english_chapter_opener_is_recognised(self):
        self.assertEqual(chapter_start('Chapter 6\nDatabase Management System'), 6)
        self.assertEqual(chapter_start('Fourth Chapter\nIntroduction to Web Design'), 4)

    def test_a_sentence_mentioning_a_chapter_number_is_not_an_opener(self):
        long_line = 'As we already explained back in chapter 6 of this book, a database stores rows.'
        self.assertIsNone(chapter_start(long_line))


class ThinPageTests(ApiTestCase):
    """A page the model returned nothing for must stay visible, or it silently never comes back."""

    def test_a_page_transcribed_to_nothing_is_thin(self):
        self.assertTrue(is_thin(''))
        self.assertTrue(is_thin('   \n  '))
        self.assertTrue(is_thin('৪.১'))

    def test_a_real_page_is_not_thin(self):
        self.assertFalse(is_thin('ক' * (MIN_PAGE_CHARS + 1)))
