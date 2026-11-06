// Search only the shared public practice catalogue. Assessment papers and the
// staff-only OCR search are deliberately not data sources for header suggestions.
import { NCTB_PROBLEMS } from '../data/problems';

const normalize = (value) => String(value || '').trim().replace(/\s+/g, ' ').toLowerCase();
let cataloguePromise;

export function buildLearningCatalog(problems) {
  const tasks = problems.map((problem) => ({
    id: problem.id,
    title: problem.title,
    chapter: problem.chapter,
    topic: problem.skill,
    type: problem.lang === 'html' ? 'HTML task' : 'C task',
    destination: '/workspace?problem=' + encodeURIComponent(problem.id),
    locked: problem.locked === true,
    keywords: normalize([problem.title, problem.chapter, problem.skill, problem.lang,
      problem.description_en, problem.description_bn, problem.difficulty].join(' ')),
  }));
  const topics = [...new Set(tasks.map((task) => task.topic).filter(Boolean))].map((topic) => {
    const matching = tasks.filter((task) => task.topic === topic);
    const firstAvailable = matching.find((task) => !task.locked);
    const chapter = [...new Set(matching.map((task) => task.chapter))].join(' · ');
    return {
      id: 'topic:' + topic, title: topic, topic, chapter, type: 'Topic',
      destination: firstAvailable?.destination || '', locked: !firstAvailable,
      keywords: normalize([topic, chapter, ...matching.map((task) => task.keywords)].join(' ')),
    };
  });
  return [...topics, ...tasks];
}

export function searchLearningCatalog(catalogue, query) {
  const normalized = normalize(query);
  if (!normalized) return [];
  const words = normalized.split(' ');
  const matches = catalogue.filter((item) => {
    const searchable = normalize([item.id, item.title, item.chapter, item.topic, item.type, item.keywords].join(' '));
    return words.every((word) => searchable.includes(word));
  });
  // A named task should open before a broad topic which only matched its keywords.
  const titleMatch = (item) => words.every((word) => normalize(item.title).includes(word)) || normalize(item.id) === normalized;
  return matches.sort((a, b) => Number(titleMatch(b)) - Number(titleMatch(a)));
}

export function loadLearningCatalog() {
  // Build the already-shared public catalogue on demand; no API or bank fetch.
  // Consumers share one promise, and an unexpected loading failure is retryable.
  if (!cataloguePromise) {
    cataloguePromise = Promise.resolve().then(() => buildLearningCatalog(NCTB_PROBLEMS))
      .catch((error) => { cataloguePromise = undefined; throw error; });
  }
  return cataloguePromise;
}
