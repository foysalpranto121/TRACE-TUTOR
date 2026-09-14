// API service for TRACE Tutor frontend with Django backend proxy & seamless offline mock fallback
import { getToken, getSessionUser, clearSession } from './session';

const API_BASE = '/api';

export class ApiError extends Error {
  constructor(message, status, fields) {
    super(message);
    this.status = status;
    this.fields = fields || {};
  }
}

// Helper for HTTP requests. `strict` endpoints surface real errors instead of silently returning mock data.
async function fetchApi(endpoint, options = {}, { strict = false } = {}) {
  const token = getToken();
  // FormData bodies must set their own multipart boundary, so no JSON content-type there.
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...options.headers,
  };

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      let fields;
      try {
        const body = await response.json();
        detail = body.error || body.detail || body.message || detail;
        fields = body.fields;
      } catch (_) {
        /* non-JSON error body */
      }
      if (response.status === 401 && token && /token|credentials/i.test(detail)) {
        clearSession();
        window.dispatchEvent(new CustomEvent('trace:session-expired'));
        detail = 'Your session has expired. Please sign in again.';
      }
      throw new ApiError(detail, response.status, fields);
    }
    return await response.json();
  } catch (error) {
    if (strict) {
      if (error instanceof ApiError) throw error;
      const msg = error.message === 'Failed to fetch' ? 'Backend server is not reachable (is Django running on port 8000?)' : error.message;
      throw new ApiError(msg, 0);
    }
    console.warn(`[TRACE API] ${endpoint} backend unavailable, falling back to mock mode:`, error.message);
    return getMockResponse(endpoint, options);
  }
}

// Mock Response Handler for robust standalone UI preview
function getMockResponse(endpoint, options) {
  if (endpoint.includes('/expert/submissions')) {
    return Promise.resolve({
      count: 1,
      submissions: [
        {
          id: 801,
          student_label: 'TT-0001',
          participant_code: 'TT-0001',
          exam_type: 'post',
          chapter: 'Chapter 5 — Programming Language (C)',
          submitted_at: '2026-09-12T21:40:00Z',
          score_pct: 80,
          correct: 12,
          total: 15,
          code_answers: [
            {
              item_id: 'post_c_code_01',
              title: 'Post-Test C Task 1: Product of First N Integers',
              question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১ থেকে N পর্যন্ত সমস্ত সংখ্যার গুণফল লুপ ব্যবহার করে নির্ণয় করবে। (Product of numbers 1 to N).',
              code: '#include <stdio.h>\n\nint main() {\n    int n;\n    long long product = 1;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        product *= i;\n    }\n    printf("Product = %lld\\n", product);\n    return 0;\n}',
              auto: { status: 'SUCCESS', passed_count: 2, total_tests: 2, detail: 'All test cases passed.' }
            }
          ],
          assigned_marks: null,
          max_marks: 100,
          feedback: '',
          status: 'PENDING_REVIEW',
          graded_by: null
        }
      ]
    });
  }

  if (endpoint.includes('/curriculum/search')) {
    const body = JSON.parse(options.body || '{}');
    return Promise.resolve({
      query: body.query,
      results_count: 3,
      passages: [
        {
          id: 'nctb_bn_chap5_01',
          chapter: 'অধ্যায় ৫: প্রোগ্রামিং ভাষা (C Programming)',
          topic: 'লুপ ও পুনরাবৃত্তি (Loops & Control Structures)',
          language: 'bn',
          passage: 'NCTB HSC ICT (বাংলা সংস্করণ) অধ্যায় ৫: C প্রোগ্রামিংয়ে নির্দিষ্টসংখ্যকবার কোনো কাজ করার জন্য for লুপ এবং শর্ত সাপেক্ষে পুনরাবৃত্তির জন্য while লুপ ব্যবহার করা হয়। লুপের প্রধান তিনটি অংশ: প্রারম্ভিক মান নির্ধারণ (initialization), শর্ত যাচাই (condition check) এবং কাউন্টারের হ্রাস-বৃদ্ধি (increment/decrement)।',
          source_ref: 'NCTB ICT Board Book Page 142 (Bangla Version)',
          similarity_score: 0.95
        },
        {
          id: 'nctb_ev_chap4_02',
          chapter: 'Chapter 4 — Web Design & HTML',
          topic: 'HTML Tables and Lists',
          language: 'en',
          passage: 'NCTB HSC ICT (English Version) Chapter 4: HTML tables are defined with the <table> tag. Table rows are created using <tr>, table headers using <th>, and data cells using <td>. To merge multiple columns or rows, the colspan and rowspan attributes are utilized respectively.',
          source_ref: 'NCTB ICT Board Book Page 98 (English Version)',
          similarity_score: 0.92
        },
        {
          id: 'nctb_bn_chap6_03',
          chapter: 'অধ্যায় ৬: ডাটাবেজ ম্যানেজমেন্ট সিস্টেম (DBMS)',
          topic: 'প্রাইমারি কি ও রিলেশনশিপ (Primary Key & SQL Queries)',
          language: 'bn',
          passage: 'NCTB HSC ICT (বাংলা সংস্করণ) অধ্যায় ৬: ডাটাবেজ টেবিলের প্রতিটি রেকর্ডকে অদ্বিতীয়ভাবে (Uniquely) শনাক্ত করার জন্য প্রাইমারি কি (Primary Key) ব্যবহার করা হয়। প্রাইমারি কি-এর মান ফাঁকা (Null) বা ডুপ্লিকেট হতে পারে না। এসকিউএল-এ টেবিল থেকে ডেটা অনুসন্ধানের জন্য SELECT কমান্ড ব্যবহার করা হয়।',
          source_ref: 'NCTB ICT Board Book Page 180 (Bangla Version)',
          similarity_score: 0.89
        }
      ]
    });
  }

  if (endpoint.includes('/tutor/query')) {
    const body = JSON.parse(options.body || '{}');
    const arm = body.arm || 'REASONING_VISIBLE';
    const problemId = body.problem_id || 'prob_assessment';

    const questionMockMap = {
      'pre_c_code_01': {
        concept: "Loop Iteration & Sum Accumulation (C Language - for loop)",
        breakdown: [
          "1. Declare variables 'n' (upper limit), 'sum = 0' (accumulator), and loop index 'i'.",
          "2. Read integer N from user using scanf.",
          "3. Iterate a for loop from i = 1 to i <= N.",
          "4. In each iteration, add 'i' to 'sum' (sum += i).",
          "5. Print the accumulated sum using printf."
        ],
        justification: "Novices often forget to initialize sum to 0 or use i < n instead of i <= n.",
        code: `#include <stdio.h>\n\nint main() {\n    int n, sum = 0;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        sum += i;\n    }\n    printf("Sum = %d\\n", sum);\n    return 0;\n}`
      },
      'post_c_code_01': {
        concept: "Loop Multiplication & Factorial Product Accumulation (for loop)",
        breakdown: [
          "1. Declare variables 'n' (upper limit), 'product = 1' (multiplicative accumulator), and loop counter 'i'.",
          "2. Read input integer N from user using scanf.",
          "3. Iterate for loop from i = 1 to i <= N.",
          "4. In each iteration, multiply 'product' by 'i' (product *= i).",
          "5. Print the calculated product."
        ],
        justification: "The initial product variable MUST be set to 1 (not 0), otherwise all multiplications result in 0.",
        code: `#include <stdio.h>\n\nint main() {\n    int n;\n    long long product = 1;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        product *= i;\n    }\n    printf("Product = %lld\\n", product);\n    return 0;\n}`
      },
      'post_c_code_02': {
        concept: "Conditional Branching & Relational Operators (if-else logic)",
        breakdown: [
          "1. Read input integer 'num' from user using scanf.",
          "2. Check condition (num > 0) for Positive numbers.",
          "3. Check condition (num < 0) for Negative numbers.",
          "4. Handle num == 0 case if required by problem specification.",
          "5. Print the classification result."
        ],
        justification: "Using relational operators (> and <) inside conditional if-else-if ladder prevents zero logic ambiguity.",
        code: `#include <stdio.h>\n\nint main() {\n    int num;\n    scanf("%d", &num);\n    if (num > 0) {\n        printf("Positive\\n");\n    } else if (num < 0) {\n        printf("Negative\\n");\n    } else {\n        printf("Zero\\n");\n    }\n    return 0;\n}`
      },
      'post_c_code_03': {
        concept: "Fibonacci Series Term Iteration (State Swapping in C)",
        breakdown: [
          "1. Initialize first two terms: t1 = 0, t2 = 1.",
          "2. Read target term index N.",
          "3. Loop from i = 2 to N to calculate nextTerm = t1 + t2.",
          "4. Update term variables: t1 = t2, t2 = nextTerm.",
          "5. Output the calculated Nth term."
        ],
        justification: "State updating order (t1=t2, t2=nextTerm) is crucial to avoid overwriting variables prematurely.",
        code: `#include <stdio.h>\n\nint main() {\n    int n;\n    scanf("%d", &n);\n    long long t1 = 0, t2 = 1, nextTerm;\n    if (n == 0) { printf("0\\n"); return 0; }\n    if (n == 1) { printf("1\\n"); return 0; }\n    for (int i = 2; i <= n; i++) {\n        nextTerm = t1 + t2;\n        t1 = t2;\n        t2 = nextTerm;\n    }\n    printf("Nth Term = %lld\\n", t2);\n    return 0;\n}`
      },
      'trans_c_code_01': {
        concept: "Mathematical Series Accumulation & Square Calculations (i * i)",
        breakdown: [
          "1. Initialize accumulator sum = 0 and read N.",
          "2. Loop i from 1 to N.",
          "3. Add (i * i) to sum in each iteration step.",
          "4. Print total sum of squares."
        ],
        justification: "Evaluating i * i before adding ensures standard mathematical precedence without needing pow() library functions.",
        code: `#include <stdio.h>\n\nint main() {\n    int n, sum = 0;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        sum += (i * i);\n    }\n    printf("Sum of Squares = %d\\n", sum);\n    return 0;\n}`
      },
      'trans_c_code_02': {
        concept: "Compound Boolean Logic & Century Year Leap Year Rules (%, &&, ||)",
        breakdown: [
          "1. Read input year.",
          "2. Check if (year % 400 == 0) OR ((year % 4 == 0) AND (year % 100 != 0)).",
          "3. Print 'Leap Year' if condition is true, otherwise print 'Not Leap Year'."
        ],
        justification: "Century years (e.g. 1900) are not leap years unless divisible by 400. Compound logic handles both cases.",
        code: `#include <stdio.h>\n\nint main() {\n    int year;\n    scanf("%d", &year);\n    if ((year % 400 == 0) || (year % 4 == 0 && year % 100 != 0)) {\n        printf("Leap Year\\n");\n    } else {\n        printf("Not Leap Year\\n");\n    }\n    return 0;\n}`
      }
    };

    const promptText = (body.prompt || '').toLowerCase().trim();
    let qInfo = null;

    if (promptText.includes('factorial') || promptText.includes('product')) {
      qInfo = {
        concept: "Factorial & Multiplicative Accumulation (for loop)",
        breakdown: [
          "1. Declare product accumulator variable long long product = 1.",
          "2. Read integer N from user input using scanf.",
          "3. Iterate for loop from i = 1 to i <= N.",
          "4. In each step, multiply product by i (product *= i).",
          "5. Print calculated factorial using format specifier %lld."
        ],
        justification: "Initializing product to 1 is mandatory because multiplying by 0 results in 0.",
        code: `#include <stdio.h>\n\nint main() {\n    int n;\n    long long product = 1;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        product *= i;\n    }\n    printf("Product = %lld\\n", product);\n    return 0;\n}`
      };
    } else if (promptText.includes('sum') || promptText.includes('add') || promptText.includes('natural')) {
      qInfo = {
        concept: "Sum Accumulation Series (for loop)",
        breakdown: [
          "1. Declare sum accumulator variable sum = 0.",
          "2. Read integer N from user input.",
          "3. Iterate for loop from i = 1 to i <= N.",
          "4. Add i to sum (sum += i) in each iteration step.",
          "5. Output total sum using printf %d."
        ],
        justification: "Initializing sum to 0 prevents garbage memory values from corrupting accumulator arithmetic.",
        code: `#include <stdio.h>\n\nint main() {\n    int n, sum = 0;\n    scanf("%d", &n);\n    for(int i = 1; i <= n; i++) {\n        sum += i;\n    }\n    printf("Sum = %d\\n", sum);\n    return 0;\n}`
      };
    } else if (promptText.includes('while')) {
      qInfo = {
        concept: "While Loop Entry-Controlled Condition Evaluation",
        breakdown: [
          "1. Initialize loop counter variable before entering while loop.",
          "2. Test condition expression inside while(condition).",
          "3. Execute loop body statements if condition is true.",
          "4. Increment or update counter variable inside loop body."
        ],
        justification: "While loops test the entry condition prior to executing the loop body.",
        code: `#include <stdio.h>\n\nint main() {\n    int i = 1, n = 5;\n    while(i <= n) {\n        printf("%d ", i);\n        i++;\n    }\n    return 0;\n}`
      };
    } else if (promptText.includes('if') || promptText.includes('else') || promptText.includes('positive') || promptText.includes('condition')) {
      qInfo = {
        concept: "Conditional Control Structure (if-else branching)",
        breakdown: [
          "1. Read input integer 'num' from user.",
          "2. Test relational condition (num > 0) for Positive classification.",
          "3. Test relational condition (num < 0) for Negative classification.",
          "4. Execute fallback else block for num == 0."
        ],
        justification: "Relational operators (>, <, ==) enable dynamic branching based on input conditions.",
        code: `#include <stdio.h>\n\nint main() {\n    int num;\n    scanf("%d", &num);\n    if (num > 0) printf("Positive\\n");\n    else if (num < 0) printf("Negative\\n");\n    else printf("Zero\\n");\n    return 0;\n}`
      };
    } else if (promptText.includes('hint')) {
      const taskObj = questionMockMap[problemId];
      qInfo = {
        concept: `Pedagogical Hint: ${taskObj?.concept || 'C Control Structure'}`,
        breakdown: [
          `1. Focus on: ${taskObj?.concept || 'Control Flow & Scope'}.`,
          "2. Check loop initialization and termination boundary (e.g. i <= N).",
          "3. Verify initial accumulator values (sum = 0 or product = 1).",
          "4. Test logic with sample inputs."
        ],
        justification: "Pedagogical hint provides key structural guidance without spoiling the full solution.",
        code: taskObj?.code || `#include <stdio.h>\n\nint main() {\n    return 0;\n}`
      };
    } else if (promptText.length > 2) {
      const topicTitle = body.prompt ? body.prompt.slice(0, 35) : "C Programming Task";
      qInfo = {
        concept: `Independent AI Explanation: ${topicTitle}`,
        breakdown: [
          `1. Answer student question: '${body.prompt || 'Analyze problem logic'}'.`,
          "2. Declare required variables with appropriate data types (int, float, char).",
          "3. Configure loop boundary or conditional branching control flow.",
          "4. Execute step-by-step logic computation.",
          "5. Display formatted output using standard printf specifiers."
        ],
        justification: `Direct answer for '${body.prompt ? body.prompt.slice(0, 50) : 'student request'}': Follow standard NCTB HSC ICT guidelines.`,
        code: `#include <stdio.h>\n\nint main() {\n    // Solution for: ${body.prompt ? body.prompt.slice(0, 30) : 'C Task'}\n    return 0;\n}`
      };
    } else {
      qInfo = questionMockMap[problemId] || {
        concept: "NCTB Curriculum Logic & Structure",
        breakdown: [
          "1. Identify input variables and required data types.",
          "2. Set initial variable values and boundary conditions.",
          "3. Apply loop iteration or conditional branching logic.",
          "4. Compute the target result.",
          "5. Output result using standard formatting."
        ],
        justification: "Verifying loop conditions and variable initializations prevents common logic errors.",
        code: `#include <stdio.h>\n\nint main() {\n    return 0;\n}`
      };
    }

    const ragMock = {
      textbook_rule: `NCTB Board Rule for ${body.prompt ? body.prompt.slice(0, 30) : problemId}: ${qInfo.concept}`,
      curriculum_citation: `NCTB HSC ICT Board Textbook (National Curriculum & Textbook Board, Chapter 5)`,
      textbook_explanation: `According to the NCTB HSC ICT textbook (Chapter 5: C Programming), algorithms and variable scoping must adhere to standard loop initializations and conditional logic.`
    };

    const indepMock = {
      concept_applied: qInfo.concept,
      problem_breakdown: qInfo.breakdown,
      pedagogical_justification: qInfo.justification,
      code_solution: qInfo.code
    };

    if (arm === 'REASONING_VISIBLE') {
      return Promise.resolve({
        mode: 'REASONING_VISIBLE',
        grounded_passage: `NCTB HSC ICT Chapter Reference for ${body.prompt ? body.prompt.slice(0, 30) : problemId}: Follow standard control structure guidelines.`,
        rag_answer: ragMock,
        independent_ai_answer: indepMock,
        reasoning_trace: indepMock
      });
    }

    return Promise.resolve({
      mode: 'ANSWER_ONLY',
      direct_answer: `Here is the solution for ${body.prompt ? body.prompt.slice(0, 30) : problemId}:\n\n${qInfo.code}`,
      rag_answer: ragMock,
      independent_ai_answer: indepMock,
      reasoning_trace: indepMock
    });
  }

  if (endpoint.includes('/assessment/items') || endpoint.includes('/assessment/questions')) {
    const isPost = endpoint.includes('type=post') || endpoint.includes('type=POST');
    const isTransfer = endpoint.includes('type=transfer') || endpoint.includes('type=TRANSFER');
    const isWithdrawal = endpoint.includes('type=withdrawal') || endpoint.includes('type=WITHDRAWAL');

    // -----------------------------------------------------------------
    // PRE-TEST ASSESSMENT SUITE (15 Baseline Knowledge Questions)
    // -----------------------------------------------------------------
    if (!isPost && !isTransfer && !isWithdrawal) {
      return Promise.resolve([
        {
          id: 'pre_c_code_01',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Pre-Test C Task 1: Sum of First N Natural Numbers',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১ থেকে N পর্যন্ত সমস্ত ধনাত্মক পূর্ণসংখ্যার যোগফল লুপের মাধ্যমে নির্ণয় করে প্রিন্ট করবে। (Write a C program to calculate the sum of numbers from 1 to N using a loop).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n, sum = 0;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 142)',
        },
        {
          id: 'pre_c_code_02',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Pre-Test C Task 2: Even or Odd Number Verification',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা প্রদত্ত সংখ্যাটি জোড় (Even) নাকি বিজোড় (Odd) তা মডুলাস (%) অপারেটর দিয়ে পরীক্ষা করবে। (Check if a given number is even or odd).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int num;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 138)',
        },
        {
          id: 'pre_c_code_03',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Pre-Test C Task 3: Factorial of a Positive Integer',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ব্যবহারকারীর প্রদত্ত ধনাত্মক সংখ্যা N-এর ফ্যাক্টোরিয়াল (N!) নির্ণয় করবে। (Calculate factorial N!).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 145)',
        },
        {
          id: 'pre_c_code_04',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Pre-Test C Task 4: Maximum of Three Numbers',
          question: 'তিনটি সংখ্যার মধ্যে বৃহত্তম সংখ্যাটি নির্ণয় করার জন্য একটি সি (C) প্রোগ্রাম লিখুন। (Find maximum of three numbers).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int a, b, c;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 140)',
        },
        {
          id: 'pre_c_code_05',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Pre-Test C Task 5: Prime Number Verification',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো প্রদত্ত পূর্ণসংখ্যা মৌলিক সংখ্যা (Prime Number) কিনা তা পরীক্ষা করে দেখাবে। (Verify prime number).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 152)',
        },

        {
          id: 'pre_html_code_01',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test HTML Task 1: Student Marks Table Structure',
          question: 'একটি এইচটিএমএল (HTML) কোড লিখুন যা ২ সারি ও ২ কলামের একটি টেবিল তৈরি করবে (Roll ও Marks হেডারসহ)। (Create a 2x2 table for Roll and Marks).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write 2x2 table for Roll and Marks here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 98)',
        },
        {
          id: 'pre_html_code_02',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test HTML Task 2: Clickable Image Hyperlink',
          question: 'এমন একটি HTML কোড লিখুন যেখানে "college.jpg" ছবিটিতে ক্লিক করলে "https://nctb.gov.bd" ওয়েবসাইটটি ওপেন হবে। (Clickable image hyperlink).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write clickable image hyperlink code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 105)',
        },
        {
          id: 'pre_html_code_03',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test HTML Task 3: Formatted Ordered List',
          question: 'এইচটিএমএল (HTML) ব্যবহার করে ১, ২, ৩ ক্রমিক নম্বরযুক্ত একটি Ordered List (<ol>) তৈরি করুন যেখানে বিষয়গুলোর নাম বোল্ড (<b>) হবে। (Formatted ordered list).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write formatted ordered list here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 92)',
        },

        {
          id: 'pre_mcq_chap4_01',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test MCQ 1: HTML Hyperlink Anchor Tag',
          question: 'এইচটিএমএল (HTML) ডকুমেন্টে অন্য কোনো ওয়েব পেজ হাইপারলিংক করার জন্য কোন ট্যাগটি ব্যবহৃত হয়? (Which tag creates a hyperlink in HTML?)',
          options: [{ id: 'a', text: '<link>' }, { id: 'b', text: '<a href="...">' }, { id: 'c', text: '<url>' }, { id: 'd', text: '<anchor>' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 86)'
        },
        {
          id: 'pre_mcq_chap4_02',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test MCQ 2: Secure Web Protocol & Default Port',
          question: 'নিরাপদ ওয়েব ডেটা আদান-প্রদানের জন্য কোন প্রোটোকল এবং পোর্ট নম্বর ব্যবহৃত হয়? (Secure protocol & port).',
          options: [{ id: 'a', text: 'HTTP (Port 80)' }, { id: 'b', text: 'HTTPS (Port 443)' }, { id: 'c', text: 'FTP (Port 21)' }, { id: 'd', text: 'SMTP (Port 25)' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 78)'
        },
        {
          id: 'pre_mcq_chap4_03',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test MCQ 3: HTML Root Structure Tags',
          question: 'একটি সঠিক ওয়েব পেজের মৌলিক এইচটিএমএল ডকুমেন্টের রুট এলিমেন্ট কোনটি? (HTML document root element).',
          options: [{ id: 'a', text: '<head>' }, { id: 'b', text: '<html>' }, { id: 'c', text: '<body>' }, { id: 'd', text: '<title>' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 82)'
        },
        {
          id: 'pre_mcq_chap4_04',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test MCQ 4: HTML Table Column Spanning Attribute',
          question: 'এইচটিএমএল (HTML) টেবিলে একাধিক কলামকে একসাথে যুক্ত করার জন্য কোন অ্যাট্রিবিউট ব্যবহৃত হয়? (Attribute to span multiple columns).',
          options: [{ id: 'a', text: 'rowspan' }, { id: 'b', text: 'colspan' }, { id: 'c', text: 'cellspacing' }, { id: 'd', text: 'cellpadding' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 100)'
        },
        {
          id: 'pre_mcq_chap4_05',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Pre-Test MCQ 5: Image Source Attribute',
          question: 'ওয়েব পেজে ছবি প্রদর্শনের জন্য <img> ট্যাগের সাথে অপরিহার্য কোন অ্যাট্রিবিউটটি ফাইলের পথ নির্দেশ করে? (Image source attribute).',
          options: [{ id: 'a', text: 'href' }, { id: 'b', text: 'src' }, { id: 'c', text: 'alt' }, { id: 'd', text: 'link' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 104)'
        },

        {
          id: 'pre_mcq_chap6_01',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Pre-Test MCQ 6: Primary Key Characteristic',
          question: 'ডাটাবেজ ম্যানেজমেন্ট সিস্টেমে (DBMS) প্রাইমারি কি (Primary Key)-এর প্রধান বৈশিষ্ট্য কোনটি? (Primary key characteristic).',
          options: [{ id: 'a', text: 'একই কলামে ডুপ্লিকেট মান থাকতে পারে' }, { id: 'b', text: 'প্রতিটি রেকর্ডকে অদ্বিতীয়ভাবে (Uniquely) শনাক্ত করে এবং Null হতে পারে না' }, { id: 'c', text: 'এটি শুধুমাত্র টেক্সট ডেটা সাজাতে ব্যবহৃত হয়' }, { id: 'd', text: 'সব ঘরের মান ফাঁকা রাখা যায়' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 180)'
        },
        {
          id: 'pre_mcq_chap6_02',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Pre-Test MCQ 7: SQL Data Retrieval Command',
          question: 'এসকিউএল (SQL)-এ ডাটাবেজ টেবিল থেকে নির্দিষ্ট ডেটা খুঁজে বের করার বা প্রদর্শনের জন্য কোন কমান্ডটি ব্যবহৃত হয়? (SQL command for data retrieval).',
          options: [{ id: 'a', text: 'EXTRACT' }, { id: 'b', text: 'SELECT' }, { id: 'c', text: 'OPEN' }, { id: 'd', text: 'GET' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 195)'
        }
      ]);
    }

    // -----------------------------------------------------------------
    // POST-TEST ASSESSMENT SUITE (15 Direct Learning Gain Questions)
    // -----------------------------------------------------------------
    if (isPost) {
      return Promise.resolve([
        {
          id: 'post_c_code_01',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 1: Product of First N Integers',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১ থেকে N পর্যন্ত সমস্ত সংখ্যার গুণফল লুপ ব্যবহার করে নির্ণয় করবে। (Write a C program to calculate the product of numbers 1 to N).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 143)',
        },
        {
          id: 'post_c_code_02',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 2: Positive or Negative Checker',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা প্রদত্ত সংখ্যাটি ধনাত্মক (Positive) নাকি ঋণাত্মক (Negative) তা if-else দিয়ে পরীক্ষা করবে। (Check positive or negative number).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int num;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 139)',
        },
        {
          id: 'post_c_code_03',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 3: Fibonacci Series Term Calculation',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ফিবোনাক্কি সিরিজের N-তম পদ নির্ণয় করে প্রদর্শন করবে (F0=0, F1=1)। (Calculate Nth Fibonacci number).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 148)',
        },
        {
          id: 'post_c_code_04',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 4: Minimum of Three Numbers',
          question: 'তিনটি পূর্ণসংখ্যার মধ্যে ক্ষুদ্রতম সংখ্যাটি (Minimum) নির্ণয় করার জন্য একটি সি (C) প্রোগ্রাম লিখুন। (Find minimum of three numbers).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int a, b, c;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 141)',
        },
        {
          id: 'post_c_code_05',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 5: Count Divisors of an Integer',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো প্রদত্ত পূর্ণসংখ্যার মোট ভাজক সংখ্যা (Count of Divisors) নির্ণয় করবে। (Count number of divisors of an integer).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 150)',
        },

        {
          id: 'post_html_code_01',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test HTML Task 1: Employee Table with Rowspan',
          question: 'একটি HTML টেবিল তৈরি করুন যেখানে "Department" সেলটি ২ টি সারি জুড়ে সম্প্রসারিত (rowspan="2") থাকবে। (Create HTML table with rowspan="2").',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write table with rowspan="2" here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 101)',
        },
        {
          id: 'post_html_code_02',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test HTML Task 2: Internal Section Bookmark Link',
          question: 'একই ওয়েব পেজের `#contact` আইডি বিশিষ্ট সেকশনে নেভিগেট করার জন্য একটি এইচটিএমএল হাইপারলিংক লিখুন। (Internal section bookmark hyperlink).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write internal section bookmark hyperlink code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 88)',
        },
        {
          id: 'post_html_code_03',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test HTML Task 3: Unordered Bullet List',
          question: 'এইচটিএমএল (HTML) ব্যবহার করে ডিস্ক (disc) স্টাইলের বুলেটযুক্ত একটি Unordered List (<ul>) তৈরি করুন। (Create unordered bullet list).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write unordered list with disc bullets here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 94)',
        },

        {
          id: 'post_mcq_chap4_01',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test MCQ 1: HTML Line Break Tag',
          question: 'এইচটিএমএল (HTML) ডকুমেন্টে নতুন লাইন বা লাইন ব্রেক তৈরি করার জন্য কোন ট্যাগটি ব্যবহৃত হয়? (Line break tag in HTML).',
          options: [{ id: 'a', text: '<p>' }, { id: 'b', text: '<br>' }, { id: 'c', text: '<hr>' }, { id: 'd', text: '<break>' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 84)'
        },
        {
          id: 'post_mcq_chap4_02',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test MCQ 2: Domain Name System (DNS) Role',
          question: 'ডোমেইন নেম সিস্টেম (DNS)-এর প্রধান কাজ কোনটি? (Primary role of Domain Name System DNS).',
          options: [{ id: 'a', text: 'এইচটিএমএল কোড এডিট করা' }, { id: 'b', text: 'ডোমেইন নেমকে আইপি (IP) অ্যাড্রেসে রূপান্তর করা' }, { id: 'c', text: 'সার্ভারে ফাইল আপলোড করা' }, { id: 'd', text: 'ডাটাবেজ কানেক্ট করা' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 76)'
        },
        {
          id: 'post_mcq_chap4_03',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test MCQ 3: Character Encoding Meta Tag',
          question: 'বাংলা ভাষা ও আন্তর্জাতিক অক্ষরের সঠিক রূপায়নের জন্য এইচটিএমএল-এ কোন চারসেট মেটা ট্যাগ যুক্ত করা হয়? (Character encoding meta tag for Bengali UTF-8).',
          options: [{ id: 'a', text: '<meta charset="ASCII">' }, { id: 'b', text: '<meta charset="UTF-8">' }, { id: 'c', text: '<meta encoding="ANSI">' }, { id: 'd', text: '<meta type="UNICODE">' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 83)'
        },
        {
          id: 'post_mcq_chap4_04',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test MCQ 4: Table Header Cell Tag',
          question: 'এইচটিএমএল টেবিলে কলামের শিরোনাম বা হেডার তৈরির জন্য কোন ট্যাগ ব্যবহৃত হয়? (Table header element tag).',
          options: [{ id: 'a', text: '<td>' }, { id: 'b', text: '<th>' }, { id: 'c', text: '<tr >' }, { id: 'd', text: '<header>' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 96)'
        },
        {
          id: 'post_mcq_chap4_05',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Post-Test MCQ 5: Anchor Target Attribute',
          question: 'হাইপারলিংকে ক্লিক করলে লিংকটি নতুন ব্রাউজার ট্যাবে খুলতে কোন target অ্যাট্রিবিউট ব্যবহার করা হয়? (Target attribute for new tab).',
          options: [{ id: 'a', text: 'target="_self"' }, { id: 'b', text: 'target="_blank"' }, { id: 'c', text: 'target="_new"' }, { id: 'd', text: 'target="_parent"' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 87)'
        },

        {
          id: 'post_mcq_chap6_01',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Post-Test MCQ 6: Foreign Key Relationship',
          question: 'দুইটি ডাটাবেজ টেবিলের মধ্যে সম্পর্ক (Relational Binding) স্থাপন করতে কোন কি (Key) ব্যবহৃত হয়? (Foreign key for relational binding).',
          options: [{ id: 'a', text: 'Super Key' }, { id: 'b', text: 'Foreign Key' }, { id: 'c', text: 'Composite Key' }, { id: 'd', text: 'Candidate Key' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 182)'
        },
        {
          id: 'post_mcq_chap6_02',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Post-Test MCQ 7: SQL Conditional WHERE Clause',
          question: 'এসকিউএল (SQL) কোয়েরিতে নির্দিষ্ট শর্ত আরোপ করে ডেটা ফিল্টার করতে কোন ক্লজ ব্যবহার করা হয়? (Conditional WHERE clause in SQL).',
          options: [{ id: 'a', text: 'HAVING' }, { id: 'b', text: 'WHERE' }, { id: 'c', text: 'GROUP BY' }, { id: 'd', text: 'ORDER BY' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 196)'
        }
      ]);
    }

    // -----------------------------------------------------------------
    // TRANSFER TEST SUITE (15 Novel Isomorphic Questions)
    // -----------------------------------------------------------------
    if (isTransfer) {
      return Promise.resolve([
        {
          id: 'trans_c_code_01',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Transfer Task 1: Sum of Squares of First N Numbers',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১^২ + ২^২ + ... + N^২ গাণিতিক ধারার যোগফল নির্ণয় করে প্রিন্ট করবে। (Calculate sum of series 1^2 + 2^2 + ... + N^2).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 146)',
        },
        {
          id: 'trans_c_code_02',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Transfer Task 2: Leap Year Verification Algorithm',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো নির্দিষ্ট বছর লিপ ইয়ার (Leap Year) কিনা তা শর্ত সাপেক্ষে যাচাই করে দেখাবে। (Leap year verification algorithm).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int year;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 137)',
        },
        {
          id: 'trans_c_code_03',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Transfer Task 3: Reverse of an Integer Digits',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো প্রদত্ত পূর্ণসংখ্যার অংকগুলো বিপরীতক্রমে (Reversed Order) সাজিয়ে প্রদর্শন করবে। (Reverse digits of an integer).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int num;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 154)',
        },
        {
          id: 'trans_c_code_04',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Transfer Task 4: Average of Three Float Numbers',
          question: 'তিনটি দশমিক সংখ্যার (Float Numbers) গড় (Average) নির্ণয় করার জন্য একটি সি (C) প্রোগ্রাম লিখুন। (Calculate average of 3 float numbers).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    float a, b, c;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 134)',
        },
        {
          id: 'trans_c_code_05',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Transfer Task 5: Armstrong Number Verification',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ৩ অংকের সংখ্যা আর্মস্ট্রং সংখ্যা (Armstrong Number: 153 = 1^3+5^3+3^3) কিনা তা পরীক্ষা করবে। (Check Armstrong number).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int num;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 156)',
        },

        {
          id: 'trans_html_code_01',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer HTML Task 1: Student Registration Form',
          question: 'নাম ইনপুট টেক্সট বক্স এবং সাবমিট বাটনসহ একটি এইচটিএমএল ফর্ম (<form>) তৈরি করার কোড লিখুন। (Student registration HTML form).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write registration form code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 108)',
        },
        {
          id: 'trans_html_code_02',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer HTML Task 2: Embedded Video Player',
          question: 'একটি ভিডিও ফাইল প্লে করার জন্য এইচটিএমএল৫ (<video>) কন্ট্রোলসহ কোড স্ট্রাকচার লিখুন। (Embedded HTML5 video player).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write video element code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 110)',
        },
        {
          id: 'trans_html_code_03',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer HTML Task 3: Nested Navigation List',
          question: 'প্রধান বিষয় এবং তার অধীনে সাব-টপিক প্রদর্শন করার জন্য একটি নেস্টেড তালিকা (Nested List) তৈরি করুন। (Multi-level nested list).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write nested list code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 95)',
        },

        {
          id: 'trans_mcq_chap4_01',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer MCQ 1: External CSS Linking Tag',
          question: 'এইচটিএমএল ডকুমেন্টের সাথে বাহ্যিক সিএসএস (External CSS) ফাইল যুক্ত করার জন্য কোন ট্যাগটি সঠিক? (External CSS linking tag).',
          options: [{ id: 'a', text: '<script src="style.css">' }, { id: 'b', text: '<link rel="stylesheet" href="style.css">' }, { id: 'c', text: '<style src="style.css">' }, { id: 'd', text: '<css href="style.css">' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 112)'
        },
        {
          id: 'trans_mcq_chap4_02',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer MCQ 2: Dynamic Website Characteristic',
          question: 'ডাইনামিক ওয়েবসাইটের (Dynamic Website) প্রধান বৈশিষ্ট্য কোনটি? (Dynamic website characteristics).',
          options: [{ id: 'a', text: 'কনটেন্ট কখনো পরিবর্তন হয় না' }, { id: 'b', text: 'ডাটাবেজের সাথে সংযোগ থাকে এবং ব্যবহারকারীর ইনপুট অনুযায়ী বিষয়বস্তু পরিবর্তিত হয়' }, { id: 'c', text: 'শুধুমাত্র এইচটিএমএল দিয়ে তৈরি হয়' }, { id: 'd', text: 'সার্ভার স্ক্রিপ্টিং সাপোর্ট করে না' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 74)'
        },
        {
          id: 'trans_mcq_chap4_03',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer MCQ 3: Form Radio Button vs Checkbox',
          question: 'ফর্মে একাধিক অপশন থেকে যেকোনো একটি মাত্র নির্বাচন করার জন্য কোন ইনপুট টাইপ ব্যবহার করা হয়? (Radio button vs checkbox).',
          options: [{ id: 'a', text: 'type="checkbox"' }, { id: 'b', text: 'type="radio"' }, { id: 'c', text: 'type="select"' }, { id: 'd', text: 'type="button"' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 107)'
        },
        {
          id: 'trans_mcq_chap4_04',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer MCQ 4: Title Tag Purpose',
          question: 'এইচটিএমএল ডকুমেন্টের <title> ট্যাগের কনটেন্ট কোথায় প্রদর্শিত হয়? (Title tag location in browser).',
          options: [{ id: 'a', text: 'ওয়েব পেজের বডির শুরুতে' }, { id: 'b', text: 'ব্রাউজারের টাইটেল বার বা ট্যাবে' }, { id: 'c', text: 'পেজের ফুটার অংশে' }, { id: 'd', text: 'সার্চ ইঞ্জিনের স্ক্রল বারে' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 81)'
        },
        {
          id: 'trans_mcq_chap4_05',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Transfer MCQ 5: Text Formatting Emphasis Tag',
          question: 'এইচটিএমএল-এ টেক্সটকে গুরুত্বপূর্ণ জোর (Emphasis) দেওয়ার জন্য কোন ট্যাগটি ব্যবহৃত হয়? (Emphasis tag <em>).',
          options: [{ id: 'a', text: '<i>' }, { id: 'b', text: '<em>' }, { id: 'c', text: '<bold>' }, { id: 'd', text: '<mark>' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 90)'
        },

        {
          id: 'trans_mcq_chap6_01',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Transfer MCQ 6: Relational Cardinalities',
          question: 'একজন শিক্ষকের অধীনে একাধিক শিক্ষার্থী থাকার সম্পর্ককে কোন রিলেশনশিপ বলা হয়? (One-to-Many cardinality).',
          options: [{ id: 'a', text: 'One-to-One' }, { id: 'b', text: 'One-to-Many' }, { id: 'c', text: 'Many-to-Many' }, { id: 'd', text: 'Self Relationship' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 186)'
        },
        {
          id: 'trans_mcq_chap6_02',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Transfer MCQ 7: SQL UPDATE Command',
          question: 'ডাটাবেজ টেবিলের বিদ্যমান ডেটা সংশোধন করার জন্য কোন এসকিউএল (SQL) কমান্ড ব্যবহৃত হয়? (SQL UPDATE command).',
          options: [{ id: 'a', text: 'MODIFY' }, { id: 'b', text: 'UPDATE' }, { id: 'c', text: 'CHANGE' }, { id: 'd', text: 'ALTER' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 198)'
        }
      ]);
    }

    // -----------------------------------------------------------------
    // WITHDRAWAL TASK SUITE (15 Independent Skill Evaluation Questions)
    // -----------------------------------------------------------------
    if (isWithdrawal) {
      return Promise.resolve([
        {
          id: 'with_c_code_01',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Withdrawal C Task 1: Sum of Odd Numbers 1 to N',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১ থেকে N পর্যন্ত সমস্ত বিজোড় পূর্ণসংখ্যার যোগফল লুপের মাধ্যমে নির্ণয় করবে। (Sum of odd numbers from 1 to N).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 144)',
        },
        {
          id: 'with_c_code_02',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Withdrawal C Task 2: Grade Point Average (GPA) Evaluator',
          question: 'পরীক্ষার নম্বর ইনপুট নিয়ে GPA গ্রেড (৮০ বা তার বেশি হলে A+, ৭০-৭৯ হলে A) প্রদর্শনের একটি C প্রোগ্রাম লিখুন। (GPA grade evaluator).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int marks;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 136)',
        },
        {
          id: 'with_c_code_03',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Withdrawal C Task 3: Power Calculation (X^Y)',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো ভিত্তি সংখ্যা X এবং পাওয়ার Y গ্রহণ করে X^Y মান নির্ণয় করবে। (Calculate power X^Y).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int base, exp;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 147)',
        },
        {
          id: 'with_c_code_04',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Withdrawal C Task 4: Swap Two Numbers Using Variable',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা একটি অস্থায়ী চলক (Temporary Variable) ব্যবহার করে ২টির ইন্টারচেঞ্জ বা সোয়াপ (Swap) করবে। (Swap two variables).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int a, b;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 133)',
        },
        {
          id: 'with_c_code_05',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Withdrawal C Task 5: Palindrome Number Verification',
          question: 'একটি সি (C) প্রোগ্রাম লিখুন যা কোনো প্রদত্ত পূর্ণসংখ্যা প্যালিনড্রোম (Palindrome: যেমন 121) কিনা তা পরীক্ষা করে দেখাবে। (Verify palindrome number).',
          code_snippet: `#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}`,
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 155)',
        },

        {
          id: 'with_html_code_01',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal HTML Task 1: Class Routine Timetable',
          question: 'হেডার কলামে colspan="2" ব্যবহার করে ক্লাসের রুটিনের একটি সমন্বিত এইচটিএমএল টেবিল তৈরি করুন। (Class routine table with colspan).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write class routine timetable here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 102)',
        },
        {
          id: 'with_html_code_02',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal HTML Task 2: Image Gallery Grid with Alt Text',
          question: 'এইচটিএমএল (HTML) ব্যবহার করে বিকল্প টেক্সটসহ (alt="Book Cover") ২ টি বইয়ের ছবির গ্রিড তৈরি করুন। (Image grid with alt text).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write image grid with alt text here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 106)',
        },
        {
          id: 'with_html_code_03',
          type: 'html_coding',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal HTML Task 3: Multi-level Navigation Bar',
          question: 'এইচটিএমএল নেভিগেশন বারের (<nav>) আওতায় ৩টি লিংকের আন-অর্ডারড তালিকা (Home, Courses, Contact) তৈরি করুন। (Navigation bar with list).',
          code_snippet: `<!DOCTYPE html>\n<html>\n<body>\n  <!-- Write navigation bar code here -->\n\n</body>\n</html>`,
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 97)',
        },

        {
          id: 'with_mcq_chap4_01',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal MCQ 1: Web Server vs Browser Roles',
          question: 'ওয়েব পেজ প্রদর্শনকারী ক্লায়েন্ট-সাইড সফটওয়্যার কোনটি? (Client-side web browser).',
          options: [{ id: 'a', text: 'Apache Server' }, { id: 'b', text: 'Web Browser (e.g. Chrome)' }, { id: 'c', text: 'MySQL Database' }, { id: 'd', text: 'PHP Engine' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 75)'
        },
        {
          id: 'with_mcq_chap4_02',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal MCQ 2: Absolute vs Relative URL Syntax',
          question: 'সম্পূর্ণ প্রোটোকল ও ডোমেইন সহ ওয়েবসাইট ঠিকানা (যেমন: https://site.com/page.html) কে কি বলা হয়? (Absolute URL vs Relative URL).',
          options: [{ id: 'a', text: 'Relative URL' }, { id: 'b', text: 'Absolute URL' }, { id: 'c', text: 'Static IP' }, { id: 'd', text: 'Local Host' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 79)'
        },
        {
          id: 'with_mcq_chap4_03',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal MCQ 3: HTML Comment Syntax',
          question: 'এইচটিএমএল সোর্স কোডে কমেন্ট (Comment) বা মন্তব্য লেখার সঠিক সিনট্যাক্স কোনটি? (HTML comment syntax <!-- -->).',
          options: [{ id: 'a', text: '// This is a comment' }, { id: 'b', text: '<!-- This is a comment -->' }, { id: 'c', text: '/* This is a comment */' }, { id: 'd', text: '# This is a comment' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 85)'
        },
        {
          id: 'with_mcq_chap4_04',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal MCQ 4: Table Cellpadding Attribute',
          question: 'টেবিল সেলের বর্ডার এবং কনটেন্টের মধ্যকার দূরত্ব নিয়ন্ত্রণ করতে কোন অ্যাট্রিবিউট ব্যবহৃত হয়? (Table cellpadding attribute).',
          options: [{ id: 'a', text: 'cellspacing' }, { id: 'b', text: 'cellpadding' }, { id: 'c', text: 'border' }, { id: 'd', text: 'margin' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 99)'
        },
        {
          id: 'with_mcq_chap4_05',
          type: 'concept_mcq',
          chapter: 'Chapter 4 — Web Design and HTML',
          title: 'Withdrawal MCQ 5: Target Attribute Default Value',
          question: 'লিংক ট্যাগে target অ্যাট্রিবিউট না দিলে ডিফল্টভাবে লিংকটি কোথায় ওপেন হয়? (Default target attribute value _self).',
          options: [{ id: 'a', text: 'নতুন উইন্ডোতে' }, { id: 'b', text: 'বর্তমান উইন্ডোতে (_self)' }, { id: 'c', text: 'ব্যাকগ্রাউন্ড ট্যাবে' }, { id: 'd', text: 'পপআপ বক্সে' }],
          curriculum_ref: 'NCTB ICT Chapter 4 (Page 87)'
        },

        {
          id: 'with_mcq_chap6_01',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Withdrawal MCQ 6: Database Indexing Purpose',
          question: 'ডাটাবেজ টেবিলে ইনডেক্সিং (Indexing) ব্যবহারের মূল উদ্দেশ্য কোনটি? (Database indexing purpose).',
          options: [{ id: 'a', text: 'মেমোরি সেভ করা' }, { id: 'b', text: 'ডেটা অনুসন্ধানের (Search) গতি বৃদ্ধি করা' }, { id: 'c', text: 'টেবিল ডিলিট করা' }, { id: 'd', text: 'পাসওয়ার্ড সুরক্ষা দেওয়া' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 190)'
        },
        {
          id: 'with_mcq_chap6_02',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Withdrawal MCQ 7: SQL DELETE vs DROP Distinction',
          question: 'ডাটাবেজ টেবিল স্ট্রাকচার অপরিবর্তিত রেখে শুধুমাত্র ভিতরের সমস্ত রেকর্ড মুছে ফেলতে কোন SQL কমান্ড ব্যবহৃত হয়? (SQL DELETE vs DROP).',
          options: [{ id: 'a', text: 'DROP TABLE' }, { id: 'b', text: 'DELETE FROM' }, { id: 'c', text: 'REMOVE' }, { id: 'd', text: 'CLEAR' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 200)'
        }
      ]);
    }
  }

  if (endpoint.includes('/expert/reviews')) {
    return Promise.resolve({
      items_to_review: [
        {
          id: 'post_c_code_01',
          exam_type: 'post',
          type: 'c_programming',
          chapter: 'Chapter 5 — Programming Language (C)',
          title: 'Post-Test C Task 1: Product of First N Integers',
          question_text: 'একটি সি (C) প্রোগ্রাম লিখুন যা ১ থেকে N পর্যন্ত সমস্ত সংখ্যার গুণফল লুপ ব্যবহার করে নির্ণয় করবে। (Product of numbers 1 to N).',
          code_snippet: '#include <stdio.h>\n\nint main() {\n    // Write your C program here\n    int n;\n    \n    return 0;\n}',
          curriculum_ref: 'NCTB ICT Chapter 5 (Page 143)',
          ratings_count: 0,
          my_rating: null
        },
        {
          id: 'post_mcq_chap6_01',
          exam_type: 'post',
          type: 'concept_mcq',
          chapter: 'Chapter 6 — Database Management System',
          title: 'Post-Test MCQ 6: Foreign Key Relationship',
          question_text: 'দুইটি ডাটাবেজ টেবিলের মধ্যে সম্পর্ক (Relational Binding) স্থাপন করতে কোন কি (Key) ব্যবহৃত হয়? (Foreign key for relational binding).',
          options: [{ id: 'a', text: 'Super Key' }, { id: 'b', text: 'Foreign Key' }, { id: 'c', text: 'Composite Key' }, { id: 'd', text: 'Candidate Key' }],
          curriculum_ref: 'NCTB ICT Chapter 6 (Page 182)',
          ratings_count: 0,
          my_rating: null
        }
      ],
      // No stored ratings means no CVI yet — the real endpoint returns null here rather than a flattering constant.
      cvi_stats: { total_items: 2, rated_items: 0, expert_count: 0, ratings_count: 0, i_cvi_pass_rate: null, s_cvi_ave: null }
    });
  }

  if (endpoint.includes('/admin/stats')) {
    return Promise.resolve({
      participants: { total: 0, students: 0, experts: 0, researchers: 0 },
      arms: { REASONING_VISIBLE: 0, ANSWER_ONLY: 0 },
      exams: { pre: { n: 0, mean: null }, post: { n: 0, mean: null }, transfer: { n: 0, mean: null }, withdrawal: { n: 0, mean: null } },
      learning_gain: { treatment: { n: 0, mean_g: null }, control: { n: 0, mean_g: null }, cohens_d: null },
      transfer_performance: { treatment: { n: 0, mean: null }, control: { n: 0, mean: null }, cohens_d: null },
      ai_dependency: { treatment: { n: 0, mean_help_per_run: null }, control: { n: 0, mean_help_per_run: null }, cohens_d: null },
      engagement: { events: 0, help_requests: 0, code_runs: 0, copy_paste: 0, active_today: 0, active_7d: 0 },
      expert: { ratings: 0, rated_items: 0, graded_submissions: 0, i_cvi_pass_rate: null, s_cvi_ave: null },
      p_values_computed: false,
      generated_at: new Date().toISOString()
    });
  }

  return Promise.resolve({});
}

function currentUser() {
  const saved = getSessionUser();
  return saved && typeof saved === 'object' ? saved : null;
}

function withUser(data = {}) {
  const u = currentUser();
  return { user_id: u?.id, username: u?.username, arm: u?.arm, ...data };
}

export const apiService = {
  getDashboard: () => {
    const u = currentUser();
    const qs = new URLSearchParams({ user_id: u?.id ?? '', username: u?.username ?? '' });
    return fetchApi(`/dashboard/?${qs}`, {}, { strict: true });
  },
  register: (registrationData) => fetchApi('/accounts/register/', { method: 'POST', body: JSON.stringify(registrationData) }, { strict: true }),
  login: (identifier, password) => fetchApi('/accounts/login/', { method: 'POST', body: JSON.stringify({ identifier, password }) }, { strict: true }),
  logout: () => fetchApi('/accounts/logout/', { method: 'POST' }, { strict: true }),
  me: () => fetchApi('/accounts/me/', {}, { strict: true }),
  updateProfile: (patch) => fetchApi('/accounts/profile/', { method: 'PATCH', body: JSON.stringify(patch) }, { strict: true }),
  uploadAvatar: (file) => {
    const body = new FormData();
    body.append('avatar', file);
    return fetchApi('/accounts/avatar/', { method: 'POST', body }, { strict: true });
  },
  deleteAvatar: () => fetchApi('/accounts/avatar/', { method: 'DELETE' }, { strict: true }),
  changePassword: (currentPassword, newPassword) =>
    fetchApi('/accounts/password/', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }, { strict: true }),
  queryTutor: (prompt, code, problemId, arm, extra = {}) =>
    fetchApi('/tutor/query/', { method: 'POST', body: JSON.stringify({ prompt, code, problem_id: problemId, arm, ...extra }) }, { strict: true }),

  // Real compiler service (compile + run test cases, or syntax-check only)
  runCode: (language, code, testCases = [], mode = 'run') =>
    fetchApi('/code/run/', { method: 'POST', body: JSON.stringify({ language, code, test_cases: testCases, mode }) }, { strict: true }),
  getCodeStatus: () => fetchApi('/code/status/', {}, { strict: true }),
  getRagStatus: () => fetchApi('/curriculum/status/', {}, { strict: true }),
  logTelemetry: (eventType, eventData) => fetchApi('/telemetry/log/', { method: 'POST', body: JSON.stringify({ event_type: eventType, event_data: withUser(eventData) }) }),
  getAssessmentItems: (type) => fetchApi(`/assessment/items/?type=${type}`, {}, { strict: true }),
  // The server grades the submission and returns { score_pct, correct, total, results }.
  submitExam: (examData) => fetchApi('/assessment/submit/', { method: 'POST', body: JSON.stringify(withUser(examData)) }, { strict: true }),
  getExpertQueue: () => fetchApi('/expert/reviews/', {}, { strict: true }),
  submitExpertRating: (itemId, ratings, feedback) => fetchApi('/expert/rating/', { method: 'POST', body: JSON.stringify({ item_id: itemId, ratings, feedback }) }, { strict: true }),
  getAdminStats: () => fetchApi('/admin/stats/'),
  
  // Student Code Submission Evaluation & Marking by Expert
  getStudentSubmissions: () => fetchApi('/expert/submissions/', {}, { strict: true }),
  gradeSubmission: (submissionId, assignedMarks, feedback) => fetchApi('/expert/grade/', { method: 'POST', body: JSON.stringify({ submission_id: submissionId, assigned_marks: assignedMarks, feedback }) }, { strict: true }),

  // Curriculum RAG Engine
  searchCurriculum: (query, language) => fetchApi('/curriculum/search/', { method: 'POST', body: JSON.stringify({ query, language }) }),
  ingestCurriculum: (opts = {}) => fetchApi('/curriculum/ingest/', { method: 'POST', body: JSON.stringify(opts) }, { strict: true }),
  getPassages: (language) => fetchApi(`/curriculum/passages/${language ? `?language=${language}` : ''}`),
};
