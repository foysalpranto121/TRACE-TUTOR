// Option lists shared by registration and the profile page. Values are stored as-is in ParticipantProfile.
export const ROLE_OPTIONS = [
  { id: 'STUDENT', title: 'শিক্ষার্থী · Student', desc: 'HSC ICT learner (Grade 11-12) taking part in the study' },
  { id: 'EXPERT_TEACHER', title: 'শিক্ষক · Teacher / Examiner', desc: 'Certifies items (CVI) and grades student code' },
  { id: 'RESEARCHER_ADMIN', title: 'গবেষক · Researcher / Admin', desc: 'Study configuration, telemetry and analytics' },
];

export const DIVISIONS = ['Dhaka', 'Chattogram', 'Rajshahi', 'Khulna', 'Barishal', 'Sylhet', 'Rangpur', 'Mymensingh'];

export const SCHOOL_SUGGESTIONS = [
  'Dhaka College', 'Notre Dame College', 'Holy Cross College', 'Viqarunnisa Noon School & College', 'Rajuk Uttara Model College',
  'Adamjee Cantonment College', 'Dhaka City College', 'Ideal School & College', 'BAF Shaheen College Dhaka', 'Dhaka Residential Model College',
  'Chittagong College', 'Rajshahi College', 'Sylhet Government College', 'Comilla Victoria Government College', 'Government Brojomohun College',
  'Khulna Public College', 'Cantonment Public School & College Rangpur', 'Ananda Mohan College', 'Carmichael College', 'Government Azizul Haque College',
];

export const SCHOOL_TYPES = [
  ['college', 'College (HSC)'], ['school_college', 'School & College'], ['madrasa', 'Alim Madrasa'],
  ['technical', 'Technical / Vocational'], ['other', 'Other'],
];
export const AREA_TYPES = [['urban', 'Urban / City'], ['semi_urban', 'Semi-urban / Upazila town'], ['rural', 'Rural / Village']];
export const GRADES = [['11', 'HSC 1st year (Grade 11)'], ['12', 'HSC 2nd year (Grade 12)']];
export const BATCH_YEARS = [['2026', 'HSC 2026'], ['2027', 'HSC 2027'], ['2028', 'HSC 2028'], ['2029', 'HSC 2029']];
export const GROUPS = [['science', 'Science'], ['business', 'Business Studies'], ['humanities', 'Humanities']];
export const MEDIUMS = [['bangla_version', 'Bangla version'], ['english_version', 'English version'], ['english_medium', 'English medium']];
export const GENDERS = [['male', 'Male'], ['female', 'Female'], ['other', 'Other'], ['undisclosed', 'Prefer not to say']];
export const EXPERIENCE = [
  ['novice', 'No programming before'], ['basic', 'Only theory / HTML in class'],
  ['intermediate', 'Wrote a few C programs'], ['advanced', 'Comfortable writing C programs'],
];
export const LANGUAGES_KNOWN = [['c', 'C'], ['html', 'HTML'], ['python', 'Python'], ['java', 'Java'], ['javascript', 'JavaScript'], ['scratch', 'Scratch']];
export const AI_FAMILIARITY = [['never', 'Never used'], ['rarely', 'Tried once or twice'], ['sometimes', 'Sometimes'], ['regularly', 'Regularly (weekly+)']];
export const DEVICES = [['laptop', 'Laptop'], ['desktop', 'Desktop PC'], ['mobile', 'Mobile phone'], ['tablet', 'Tablet'], ['shared_lab', 'Shared school lab']];
export const INTERNET = [['broadband', 'Home broadband / Wi-Fi'], ['mobile_data', 'Mobile data only'], ['both', 'Both'], ['none', 'No regular access']];
export const STUDY_HOURS = [['1', '0-2 hours / week'], ['4', '3-5 hours / week'], ['8', '6-10 hours / week'], ['12', 'More than 10 hours / week']];
export const GOALS = [
  ['programming_fundamentals', 'Programming fundamentals'], ['problem_solving', 'Problem solving'], ['algorithms', 'Algorithms & flowcharts'],
  ['debugging', 'Finding bugs'], ['html_web', 'HTML / web design'], ['exam_prep', 'HSC exam preparation'],
];
export const UI_LANGUAGES = [['bn', 'বাংলা (Bangla)'], ['en', 'English']];

// Tutor modes (study arms). Students may switch their own mode; every change is logged.
export const ARM_OPTIONS = [
  {
    id: 'REASONING_VISIBLE',
    title: 'Reasoning-Visible',
    bn: 'যুক্তি দৃশ্যমান',
    desc_bn: 'AI ধাপে ধাপে যুক্তি, পাঠ্যবইয়ের উদ্ধৃতি ও কোডের ব্যাখ্যা দেখাবে।',
    desc_en: 'The tutor shows step-by-step reasoning, NCTB textbook citations and a worked explanation.',
  },
  {
    id: 'ANSWER_ONLY',
    title: 'Answer-Only',
    bn: 'শুধু উত্তর',
    desc_bn: 'AI শুধু সরাসরি উত্তর ও কোড দেবে, কোনো ধাপে ধাপে ব্যাখ্যা ছাড়াই।',
    desc_en: 'The tutor gives only the direct answer and code, without the reasoning trace.',
  },
];

export const armLabel = (arm) => ARM_OPTIONS.find((a) => a.id === arm)?.title || 'Not assigned';

export const CONSENT_VERSION = 'v1';
export const CONSENT_POINTS = [
  'TRACE Tutor is part of a controlled study on AI tutoring for the NCTB HSC ICT syllabus. Participation is voluntary.',
  'You are assigned at random to one of two tutor modes (Reasoning-Visible or Answer-Only). You cannot choose the mode.',
  'Your code, tutor questions, test scores and clicks are logged and stored under a pseudonymous participant code (e.g. TT-0042), never your name.',
  'Only the research team can link the code to your account; published results are fully anonymised.',
  'You may withdraw at any time by contacting the research coordinator; your data will then be deleted on request.',
];

export const labelOf = (options, value) => (options.find(([v]) => v === value) || [null, value])[1] || '-';
