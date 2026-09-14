import React, { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { Brain, BookOpen, CheckCircle2, Sliders, ShieldCheck, AlertCircle, BarChart2, UserCheck, Play, Award, FileCode, CheckSquare } from 'lucide-react';

export const ExpertPortal = () => {
  const [activeTab, setActiveTab] = useState('cvi_certification'); // 'cvi_certification' or 'student_marking'
  
  // Tab 1: CVI Certification State
  const [reviewData, setReviewData] = useState(null);
  const [activeItemIndex, setActiveItemIndex] = useState(0);
  const [ratings, setRatings] = useState({
    alignment: 4,
    accuracy: 4,
    clarity: 4,
    difficulty: 3,
    answerability: 4,
  });
  const [cviFeedback, setCviFeedback] = useState('');

  // Tab 2: Student Submission Marking State
  const [submissions, setSubmissions] = useState([]);
  const [activeSubIndex, setActiveSubIndex] = useState(0);
  const [assignedMarks, setAssignedMarks] = useState(90);
  const [teacherFeedback, setTeacherFeedback] = useState('Good use of accumulator pattern and loop condition.');
  const [gradeStatus, setGradeStatus] = useState(null);

  useEffect(() => {
    loadQueue();
    loadStudentSubmissions();
  }, []);

  const loadQueue = async () => {
    const data = await apiService.getExpertQueue();
    setReviewData(data);
  };

  const loadStudentSubmissions = async () => {
    const data = await apiService.getStudentSubmissions();
    setSubmissions(data.submissions || []);
    if (data.submissions?.length > 0) {
      setAssignedMarks(data.submissions[0].assigned_marks);
      setTeacherFeedback(data.submissions[0].feedback);
    }
  };

  const handleRatingChange = (criterion, val) => {
    setRatings((prev) => ({ ...prev, [criterion]: Number(val) }));
  };

  const handleSubmitCviReview = async () => {
    const item = reviewData?.items_to_review?.[activeItemIndex];
    if (!item) return;

    await apiService.submitExpertRating(item.id, ratings, cviFeedback);

    setCviFeedback('');
    if (activeItemIndex < (reviewData?.items_to_review?.length || 1) - 1) {
      setActiveItemIndex((prev) => prev + 1);
    }
  };

  const handleGradeSubmission = async () => {
    const currentSub = submissions[activeSubIndex];
    if (!currentSub) return;

    setGradeStatus('Saving assigned marks into PostgreSQL database...');
    const res = await apiService.gradeSubmission(currentSub.id, assignedMarks, teacherFeedback);
    
    setGradeStatus(`Successfully assigned ${assignedMarks}/100 marks to ${currentSub.student_name}.`);
    setTimeout(() => setGradeStatus(null), 3000);

    if (activeSubIndex < submissions.length - 1) {
      const nextIdx = activeSubIndex + 1;
      setActiveSubIndex(nextIdx);
      setAssignedMarks(submissions[nextIdx].assigned_marks);
      setTeacherFeedback(submissions[nextIdx].feedback);
    }
  };

  const activeItem = reviewData?.items_to_review?.[activeItemIndex];
  const stats = reviewData?.cvi_stats;
  const activeSub = submissions[activeSubIndex];

  return (
    <div className="space-y-8 select-none">
      {/* Header & Tab Selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant/20 pb-4">
        <div>
          <h1 className="text-2xl font-extrabold text-on-surface flex items-center gap-2">
            <Brain className="w-7 h-7 text-primary" /> Expert Teacher & Examiner Workbench
          </h1>
          <p className="text-xs text-on-surface-variant font-medium">
            Certify RAG Question Items & Evaluate Student Code Test Submissions
          </p>
        </div>

        {/* Dual Workbench Tabs */}
        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-xl border border-outline-variant/30 text-xs font-semibold shadow-sm">
          <button
            onClick={() => setActiveTab('cvi_certification')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'cvi_certification' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <Sliders className="w-4 h-4" /> 1. Question Bank CVI Certification
          </button>
          <button
            onClick={() => setActiveTab('student_marking')}
            className={`px-4 py-2 rounded-lg transition-all flex items-center gap-2 ${
              activeTab === 'student_marking' ? 'bg-primary text-on-primary font-bold shadow-sm' : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            <UserCheck className="w-4 h-4" /> 2. Student Code Test Marking ({submissions.length})
          </button>
        </div>
      </div>

      {/* TAB 1: CVI QUESTION BANK CERTIFICATION */}
      {activeTab === 'cvi_certification' && (
        <div className="space-y-6">
          {/* CVI Metrics Summary Badge Bar */}
          {stats && (
            <div className="flex items-center gap-4 bg-surface-container p-4 rounded-2xl border border-outline-variant/30 text-xs font-mono shadow-sm">
              <div>
                <span className="text-on-surface-variant font-semibold block text-[10px]">I-CVI Threshold</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-extrabold text-sm">{(stats.i_cvi_pass_rate * 100).toFixed(0)}% (≥ 78%)</span>
              </div>
              <div className="h-6 w-px bg-outline-variant/30" />
              <div>
                <span className="text-on-surface-variant font-semibold block text-[10px]">S-CVI / Ave</span>
                <span className="text-primary font-extrabold text-sm">{stats.s_cvi_ave.toFixed(2)} (≥ 0.90)</span>
              </div>
              <div className="h-6 w-px bg-outline-variant/30" />
              <div>
                <span className="text-on-surface-variant font-semibold block text-[10px]">Fleiss' κ</span>
                <span className="text-secondary font-extrabold text-sm">{stats.fleiss_kappa}</span>
              </div>
            </div>
          )}

          {activeItem && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Item + Curriculum Source Passage (7 cols) */}
              <div className="lg:col-span-7 space-y-5">
                <div className="bg-surface-container p-5 rounded-2xl border border-primary/30 space-y-2 shadow-sm">
                  <span className="text-xs font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider font-mono">
                    <BookOpen className="w-4 h-4" /> NCTB Curriculum Source Passage
                  </span>
                  <blockquote className="text-xs text-on-surface font-medium italic bg-surface-container-lowest p-3.5 rounded-xl border border-outline-variant/20 leading-relaxed">
                    "{activeItem.source_passage}"
                  </blockquote>
                </div>

                <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-4 shadow-xl">
                  <div className="flex items-center justify-between">
                    <span className="px-2.5 py-0.5 rounded-full bg-secondary/10 text-secondary text-[11px] font-mono border border-secondary/30 font-bold">
                      Bloom Level: {activeItem.bloom_level}
                    </span>
                    <span className="text-xs text-on-surface-variant font-mono">Item ID: {activeItem.id}</span>
                  </div>

                  <h3 className="text-base font-bold text-on-surface leading-snug">
                    {activeItem.question_text}
                  </h3>

                  {activeItem.generated_code && (
                    <div className="bg-slate-900 dark:bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto">
                      <pre className="font-mono text-xs text-cyan-300 dark:text-primary leading-relaxed">
                        {activeItem.generated_code}
                      </pre>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: 5 CVI Rubric Evaluation Sliders (5 cols) */}
              <div className="lg:col-span-5 bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-6 shadow-2xl">
                <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2 uppercase tracking-wider border-b border-outline-variant/20 pb-3">
                  <Sliders className="w-4 h-4 text-primary" /> Content Validity Rubric (1-4 Scale)
                </h3>

                <div className="space-y-4 text-xs font-medium">
                  <div className="space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-on-surface">1. Curriculum Alignment</span>
                      <span className="text-primary font-mono">{ratings.alignment} / 4</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="4"
                      value={ratings.alignment}
                      onChange={(e) => handleRatingChange('alignment', e.target.value)}
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-on-surface">2. Technical & Factual Accuracy</span>
                      <span className="text-primary font-mono">{ratings.accuracy} / 4</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="4"
                      value={ratings.accuracy}
                      onChange={(e) => handleRatingChange('accuracy', e.target.value)}
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-on-surface">3. Language Clarity (Bangla/English)</span>
                      <span className="text-primary font-mono">{ratings.clarity} / 4</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="4"
                      value={ratings.clarity}
                      onChange={(e) => handleRatingChange('clarity', e.target.value)}
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-on-surface">4. Grade 11-12 Difficulty</span>
                      <span className="text-primary font-mono">{ratings.difficulty} / 4</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="4"
                      value={ratings.difficulty}
                      onChange={(e) => handleRatingChange('difficulty', e.target.value)}
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex justify-between font-bold">
                      <span className="text-on-surface">5. Defensible Answerability</span>
                      <span className="text-primary font-mono">{ratings.answerability} / 4</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="4"
                      value={ratings.answerability}
                      onChange={(e) => handleRatingChange('answerability', e.target.value)}
                      className="w-full accent-primary cursor-pointer"
                    />
                  </div>
                </div>

                <div className="space-y-1.5 pt-2">
                  <label className="text-[11px] font-bold text-on-surface uppercase tracking-wider block">
                    Expert Comments / Wording Correction
                  </label>
                  <textarea
                    rows="2"
                    value={cviFeedback}
                    onChange={(e) => setCviFeedback(e.target.value)}
                    placeholder="Suggest corrections or distractor improvements..."
                    className="w-full bg-surface-container-high rounded-xl p-3 text-xs text-on-surface border border-outline-variant/30 outline-none"
                  />
                </div>

                <button
                  onClick={handleSubmitCviReview}
                  className="w-full py-3 rounded-xl bg-primary hover:bg-primary-container text-on-primary font-bold text-xs shadow-lg shadow-primary/20 flex items-center justify-center gap-2 transition-all"
                >
                  <CheckCircle2 className="w-4 h-4" /> Certify & Submit Ratings
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: STUDENT CODE SUBMISSION MARKING & EVALUATION WORKBENCH */}
      {activeTab === 'student_marking' && (
        <div className="space-y-6">
          {gradeStatus && (
            <div className="bg-emerald-500/10 border border-emerald-500/30 p-4 rounded-xl text-xs text-emerald-600 dark:text-emerald-400 font-mono font-bold flex items-center gap-2 shadow-sm">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {gradeStatus}
            </div>
          )}

          {activeSub && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Student Code Submission & Execution Output (7 cols) */}
              <div className="lg:col-span-7 space-y-5">
                {/* Submission Meta Card */}
                <div className="bg-surface-container p-5 rounded-2xl border border-outline-variant/30 flex items-center justify-between shadow-sm">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-extrabold text-sm">
                      {activeSub.student_name[0]}
                    </div>
                    <div>
                      <h3 className="text-sm font-extrabold text-on-surface">{activeSub.student_name}</h3>
                      <span className="text-xs text-on-surface-variant font-mono font-medium">{activeSub.exam_type}</span>
                    </div>
                  </div>

                  <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono text-xs font-bold border border-emerald-500/30">
                    {activeSub.auto_test_results}
                  </span>
                </div>

                {/* Submitted C Code View */}
                <div className="bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-3 shadow-xl">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-extrabold text-on-surface uppercase tracking-wider flex items-center gap-1.5">
                      <FileCode className="w-4 h-4 text-primary" /> Submitted C Code Solution
                    </span>
                    <span className="text-xs font-mono text-on-surface-variant">Submitted: {activeSub.submitted_at}</span>
                  </div>

                  <div className="bg-slate-900 dark:bg-surface-container-lowest p-4 rounded-xl border border-outline-variant/30 overflow-x-auto shadow-inner">
                    <pre className="font-mono text-xs text-cyan-300 dark:text-primary leading-relaxed whitespace-pre-wrap">
                      {activeSub.student_code}
                    </pre>
                  </div>
                </div>
              </div>

              {/* Right Column: Expert Teacher Marking & Feedback Panel (5 cols) */}
              <div className="lg:col-span-5 bg-surface-container p-6 rounded-2xl border border-outline-variant/30 space-y-6 shadow-2xl">
                <h3 className="text-sm font-extrabold text-on-surface flex items-center gap-2 uppercase tracking-wider border-b border-outline-variant/20 pb-3">
                  <Award className="w-4 h-4 text-primary" /> Teacher Evaluation & Marking Panel
                </h3>

                {/* Marks Input (0 to 100) */}
                <div className="space-y-2">
                  <label className="text-xs font-extrabold text-on-surface uppercase tracking-wider block flex justify-between">
                    <span>Assigned Marks (0 - 100)</span>
                    <span className="text-primary font-mono text-sm">{assignedMarks} / 100</span>
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={assignedMarks}
                    onChange={(e) => setAssignedMarks(Number(e.target.value))}
                    className="w-full bg-surface-container-high rounded-xl p-3.5 text-base text-on-surface font-mono font-extrabold border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                  />
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={assignedMarks}
                    onChange={(e) => setAssignedMarks(Number(e.target.value))}
                    className="w-full accent-primary cursor-pointer mt-2"
                  />
                </div>

                {/* Qualitative Feedback */}
                <div className="space-y-2">
                  <label className="text-xs font-extrabold text-on-surface uppercase tracking-wider block">
                    Qualitative Feedback & Comments
                  </label>
                  <textarea
                    rows="4"
                    value={teacherFeedback}
                    onChange={(e) => setTeacherFeedback(e.target.value)}
                    placeholder="Write detailed feedback on loop syntax, logic breakdown, and style..."
                    className="w-full bg-surface-container-high rounded-xl p-3.5 text-xs text-on-surface font-medium border border-outline-variant/30 outline-none focus:border-primary shadow-sm"
                  />
                </div>

                {/* Action Submit Button */}
                <button
                  onClick={handleGradeSubmission}
                  className="w-full py-3.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white font-bold text-xs shadow-lg shadow-emerald-500/25 flex items-center justify-center gap-2 transition-all hover:scale-[1.02]"
                >
                  <CheckSquare className="w-4 h-4" /> Save Marks & Complete Review
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
