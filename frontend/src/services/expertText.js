// Expert UI copy follows the language provided by AuthContext.
const messages = {
  'Your assigned work': { bn: 'আপনার নির্ধারিত কাজ', en: 'Your assigned work' },
  'Assigned': { bn: 'নির্ধারিত কাজ', en: 'Assigned' },
  'Earlier work': { bn: 'আগের মূল্যায়ন', en: 'Earlier work' },
  'More': { bn: 'আরও (More)', en: 'More' },
  'Completed': { bn: 'সম্পন্ন', en: 'Completed' },
  'Remaining': { bn: 'বাকি', en: 'Remaining' },
  'Work list': { bn: 'কাজের তালিকা', en: 'Work list' },
  'No items in this work list. Choose More to review other items.': {
    bn: 'এই তালিকায় কোনো আইটেম নেই। অন্য আইটেম দেখতে আরও (More) বেছে নিন।',
    en: 'No items in this work list. Choose More to review other items.',
  },
  'No submissions in this work list. Choose More to review other submissions.': {
    bn: 'এই তালিকায় কোনো সাবমিশন নেই। অন্য সাবমিশন দেখতে আরও (More) বেছে নিন।',
    en: 'No submissions in this work list. Choose More to review other submissions.',
  },
  "Item": { bn: 'আইটেম', en: 'Item' },
  "Not graded": { bn: 'মূল্যায়ন হয়নি', en: 'Not graded' },
  "Grading…": { bn: 'মূল্যায়ন চলছে…', en: 'Grading…' },
  "Score unavailable": { bn: 'স্কোর পাওয়া যায়নি', en: 'Score unavailable' },
  "Retry": {
    "bn": "আবার চেষ্টা করুন (Retry)",
    "en": "Retry"
  },
  "Unassigned": {
    "bn": "অনির্ধারিত",
    "en": "Unassigned"
  },
  "Please enter a mark from 0 to 100.": {
    "bn": "নম্বর লিখুন — ০ থেকে ১০০ (enter a mark from 0 to 100).",
    "en": "Please enter a mark from 0 to 100."
  },
  "Expert workbench": {
    "bn": "এক্সপার্ট ওয়ার্কবেঞ্চ",
    "en": "Expert workbench"
  },
  "Item certification & student code marking": {
    "bn": "প্রশ্ন ব্যাংক সার্টিফিকেশন ও শিক্ষার্থীর কোড মূল্যায়ন (Item certification & student code marking)",
    "en": "Item certification & student code marking"
  },
  "CVI certification": {
    "bn": "CVI সার্টিফিকেশন",
    "en": "CVI certification"
  },
  "Code grading": {
    "bn": "কোড মূল্যায়ন",
    "en": "Code grading"
  },
  "Could not load the review queue:": {
    "bn": "রিভিউ কিউ লোড করা যায়নি (could not load the review queue):",
    "en": "Could not load the review queue:"
  },
  "Total items in the bank": {
    "bn": "ব্যাংকের মোট আইটেম",
    "en": "Total items in the bank"
  },
  "Items with ratings": {
    "bn": "রেটিং পাওয়া আইটেম",
    "en": "Items with ratings"
  },
  "Experts who submitted ratings": {
    "bn": "রেটিংদাতা এক্সপার্ট",
    "en": "Experts who submitted ratings"
  },
  "Stored rating records": {
    "bn": "সংরক্ষিত রেটিং সারি",
    "en": "Stored rating records"
  },
  "No ratings yet": {
    "bn": "এখনো কোনো রেটিং নেই (No ratings yet)",
    "en": "No ratings yet"
  },
  "I-CVI and S-CVI/Ave are calculated from stored expert ratings. Actual values appear after ratings are submitted.": {
    "bn": "I-CVI ও S-CVI/Ave কেবল সংরক্ষিত এক্সপার্ট রেটিং থেকে হিসাব হয়। রেটিং জমা পড়লে এখানে প্রকৃত মান দেখা যাবে।",
    "en": "I-CVI and S-CVI/Ave are calculated from stored expert ratings. Actual values appear after ratings are submitted."
  },
  "Average I-CVI of rated items": {
    "bn": "রেটিং পাওয়া আইটেমগুলোর গড় I-CVI",
    "en": "Average I-CVI of rated items"
  },
  "Rating not saved:": {
    "bn": "রেটিং সংরক্ষণ করা যায়নি (rating not saved):",
    "en": "Rating not saved:"
  },
  "Saved:": {
    "bn": "সংরক্ষিত (saved):",
    "en": "Saved:"
  },
  "No items to review": {
    "bn": "রিভিউ করার মতো কোনো আইটেম নেই (No items to review)",
    "en": "No items to review"
  },
  "There are no items in the question bank yet.": {
    "bn": "প্রশ্ন ব্যাংকে এখনো কোনো আইটেম পাওয়া যায়নি।",
    "en": "There are no items in the question bank yet."
  },
  "Previous": {
    "bn": "আগের",
    "en": "Previous"
  },
  "Next": {
    "bn": "পরের",
    "en": "Next"
  },
  "You rated this": {
    "bn": "আপনার রেটিং আছে (you rated this)",
    "en": "You rated this"
  },
  "Content validity rubric": {
    "bn": "কনটেন্ট ভ্যালিডিটি রুব্রিক",
    "en": "Content validity rubric"
  },
  "Expert comments": {
    "bn": "এক্সপার্ট মন্তব্য (Expert comments)",
    "en": "Expert comments"
  },
  "Suggest improvements to wording or distractors…": {
    "bn": "শব্দচয়ন বা ডিস্ট্র্যাক্টর সংশোধনের প্রস্তাব...",
    "en": "Suggest improvements to wording or distractors…"
  },
  "Update rating": {
    "bn": "রেটিং হালনাগাদ করুন (Update)",
    "en": "Update rating"
  },
  "Submit rating": {
    "bn": "রেটিং জমা দিন (Submit)",
    "en": "Submit rating"
  },
  "Score all five criteria first": {
    "bn": "পাঁচটি মানদণ্ডেই স্কোর দিন (score all five criteria first)",
    "en": "Score all five criteria first"
  },
  "Could not load submissions:": {
    "bn": "সাবমিশন লোড করা যায়নি (could not load submissions):",
    "en": "Could not load submissions:"
  },
  "No submissions yet": {
    "bn": "এখনো কোনো সাবমিশন নেই (No submissions yet)",
    "en": "No submissions yet"
  },
  "Student submissions will appear here after they submit their exams.": {
    "bn": "শিক্ষার্থীরা পরীক্ষা জমা দিলে সেগুলো এখানে দেখা যাবে।",
    "en": "Student submissions will appear here after they submit their exams."
  },
  "Graded": {
    "bn": "মূল্যায়িত",
    "en": "Graded"
  },
  "Pending": {
    "bn": "অপেক্ষমাণ",
    "en": "Pending"
  },
  "Pseudonymous participant code": {
    "bn": "ছদ্মনাম অংশগ্রহণকারী কোড (pseudonymous participant code)",
    "en": "Pseudonymous participant code"
  },
  "Username": {
    "bn": "ব্যবহারকারী নাম (username)",
    "en": "Username"
  },
  "Score verified by the server": {
    "bn": "সার্ভারে যাচাই করা স্কোর",
    "en": "Score verified by the server"
  },
  "Correct answers": {
    "bn": "সঠিক উত্তর",
    "en": "Correct answers"
  },
  "Not yet marked": {
    "bn": "এখনো মূল্যায়ন হয়নি",
    "en": "Not yet marked"
  },
  "Dates & time": {
    "bn": "তারিখ ও সময় (Dates & time)",
    "en": "Dates & time"
  },
  "Dhaka time · elapsed time is calculated separately for each exam": {
    "bn": "ঢাকা সময় · প্রতিটি পরীক্ষার সময় আলাদাভাবে গণনা করা হয়েছে",
    "en": "Dhaka time · elapsed time is calculated separately for each exam"
  },
  "Exam opened": {
    "bn": "পরীক্ষা খোলা",
    "en": "Exam opened"
  },
  "Submitted": {
    "bn": "জমা দেওয়া",
    "en": "Submitted"
  },
  "Time spent on this exam": {
    "bn": "এই পরীক্ষায় অতিবাহিত সময়",
    "en": "Time spent on this exam"
  },
  "Total study time": {
    "bn": "পুরো ধারাটির মোট সময়",
    "en": "Total study time"
  },
  "Not yet completed": {
    "bn": "এখনো সম্পূর্ণ হয়নি",
    "en": "Not yet completed"
  },
  "Study started": {
    "bn": "শুরু",
    "en": "Study started"
  },
  "All exams completed": {
    "bn": "সব পরীক্ষা শেষ",
    "en": "All exams completed"
  },
  "Participation window": {
    "bn": "অংশগ্রহণের সময়সীমা",
    "en": "Participation window"
  },
  "Submitted code": {
    "bn": "জমা দেওয়া কোড",
    "en": "Submitted code"
  },
  "No code answers": {
    "bn": "কোনো কোড উত্তর নেই (No code answers)",
    "en": "No code answers"
  },
  "No coding answers were found in this submission.": {
    "bn": "এই সাবমিশনে কোডিং আইটেমের উত্তর পাওয়া যায়নি।",
    "en": "No coding answers were found in this submission."
  },
  "(No code submitted)": {
    "bn": "(কোনো কোড জমা পড়েনি — no code submitted)",
    "en": "(No code submitted)"
  },
  "Marks & feedback": {
    "bn": "নম্বর ও মতামত",
    "en": "Marks & feedback"
  },
  "Not saved:": {
    "bn": "সংরক্ষণ করা যায়নি (not saved):",
    "en": "Not saved:"
  },
  "Assigned marks": {
    "bn": "প্রদত্ত নম্বর (Assigned marks)",
    "en": "Assigned marks"
  },
  "Qualitative feedback": {
    "bn": "গুণগত মতামত (Qualitative feedback)",
    "en": "Qualitative feedback"
  },
  "Write feedback on loop conditions, logic and code style…": {
    "bn": "লুপের শর্ত, লজিক ও কোড স্টাইল নিয়ে মতামত লিখুন...",
    "en": "Write feedback on loop conditions, logic and code style…"
  },
  "Save marks": {
    "bn": "নম্বর সংরক্ষণ করুন (Save marks)",
    "en": "Save marks"
  },
  "Items in bank": {
    "bn": "ব্যাংকের আইটেম",
    "en": "Items in bank"
  },
  "Rated items": {
    "bn": "রেটিং পাওয়া আইটেম",
    "en": "Rated items"
  },
  "Experts": {
    "bn": "এক্সপার্ট",
    "en": "Experts"
  },
  "Ratings stored": {
    "bn": "সংরক্ষিত রেটিং",
    "en": "Ratings stored"
  },
  "I-CVI pass rate": {
    "bn": "I-CVI উত্তীর্ণের হার",
    "en": "I-CVI pass rate"
  },
  "S-CVI / Ave": {
    "bn": "S-CVI / Ave",
    "en": "S-CVI / Ave"
  },
  "Content validity rubric (1-4 scale)": {
    "bn": "কনটেন্ট ভ্যালিডিটি রুব্রিক (১–৪ স্কেল)",
    "en": "Content validity rubric (1-4 scale)"
  },
  "Server score": {
    "bn": "সার্ভার স্কোর",
    "en": "Server score"
  },
  "Correct": {
    "bn": "সঠিক",
    "en": "Correct"
  },
  "Expert marks": {
    "bn": "এক্সপার্টের নম্বর",
    "en": "Expert marks"
  },
  "Expert marks & feedback": {
    "bn": "এক্সপার্টের নম্বর ও মতামত",
    "en": "Expert marks & feedback"
  },
  "Discard draft and load latest rating": {
    "bn": "খসড়া বাদ দিয়ে সর্বশেষ রেটিং দেখুন",
    "en": "Discard draft and load latest rating"
  },
  "Load latest marks (discard edits)": {
    "bn": "সম্পাদনা বাদ দিয়ে সর্বশেষ নম্বর দেখুন",
    "en": "Load latest marks (discard edits)"
  },
  "Refresh submissions": {
    "bn": "সাবমিশন রিফ্রেশ করুন",
    "en": "Refresh submissions"
  },
  "Unsaved draft · kept while this portal is open. Submit before leaving or refreshing.": {
    "bn": "অসম্পূর্ণ খসড়া · পোর্টাল খোলা থাকা পর্যন্ত সংরক্ষিত। বের হওয়া বা রিফ্রেশ করার আগে জমা দিন।",
    "en": "Unsaved draft · kept while this portal is open. Submit before leaving or refreshing."
  },
  "Unsaved draft · kept while this portal is open. Save before leaving or refreshing.": {
    "bn": "অসম্পূর্ণ খসড়া · পোর্টাল খোলা থাকা পর্যন্ত সংরক্ষিত। বের হওয়া বা রিফ্রেশ করার আগে নম্বর সংরক্ষণ করুন।",
    "en": "Unsaved draft · kept while this portal is open. Save before leaving or refreshing."
  },
  "I-CVI ≥ 0.78 threshold": {
    "bn": "I-CVI ≥ 0.78 সীমা",
    "en": "I-CVI ≥ 0.78 threshold"
  },
  "ratings": {
    "bn": "রেটিং",
    "en": "ratings"
  },
  "Submissions": {
    "bn": "সাবমিশন",
    "en": "Submissions"
  },
  "newest first": {
    "bn": "সর্বশেষ আগে",
    "en": "newest first"
  },
  "Automatic": {
    "bn": "স্বয়ংক্রিয়",
    "en": "Automatic"
  },
  "Marks": {
    "bn": "নম্বর",
    "en": "Marks"
  },
  "Submission": {
    "bn": "সাবমিশন",
    "en": "Submission"
  },
  "Submitted:": {
    "bn": "জমা:",
    "en": "Submitted:"
  },
  "Marked by:": {
    "bn": "মূল্যায়ন:",
    "en": "Marked by:"
  },
  "Submitted code answers": {
    "bn": "জমা দেওয়া কোড উত্তর",
    "en": "Submitted code answers"
  },
  "tests passed": {
    "bn": "টেস্ট পাস",
    "en": "tests passed"
  },
  "Pre-test": {
    "bn": "প্রি-টেস্ট (pre)",
    "en": "Pre-test"
  },
  "Post-test": {
    "bn": "পোস্ট-টেস্ট (post)",
    "en": "Post-test"
  },
  "Transfer": {
    "bn": "ট্রান্সফার (transfer)",
    "en": "Transfer"
  },
  "Withdrawal": {
    "bn": "উইথড্রয়াল (withdrawal)",
    "en": "Withdrawal"
  }
};

export const expertText = (language, key) => messages[key]?.[language === 'en' ? 'en' : 'bn'] ?? key;

// Assessment wording remains as authored, independently of the interface language.
export const contentLanguage = (text) => /[\u0980-\u09ff]/u.test(text || '') ? 'bn' : 'en';
