// Only server responses determine eligibility. Coalesce overlapping checks and
// ignore responses older than an assessment change or a tutor policy rejection.
export function createTutorAvailability(fetchDashboard, onDashboard = () => {}) {
  let state = { status: 'checking', examType: null, error: null };
  let revision = 0;
  let inFlight = null;
  let refreshAgain = false;
  let nextBackground = true;
  const listeners = new Set();
  const publish = (next) => {
    if (state.status === next.status && state.examType === next.examType && state.error === next.error) return;
    state = next;
    listeners.forEach((listener) => listener());
  };
  const refresh = ({ background = false } = {}) => {
    if (inFlight) return inFlight;
    const started = revision;
    if (!background || !['available', 'locked'].includes(state.status)) {
      publish({ ...state, status: 'checking', error: null });
    }
    inFlight = Promise.resolve().then(fetchDashboard).then((data) => {
      if (started !== revision) return state;
      const availability = data?.tutor_availability;
      if (typeof availability?.available !== 'boolean') {
        throw new Error('Tutor availability was not returned by the server.');
      }
      publish({ status: availability.available ? 'available' : 'locked',
        examType: availability.exam_type || null, error: null });
      onDashboard(data);
      return state;
    }).catch((error) => {
      if (started === revision) publish({ ...state, status: 'error', error: error.message });
      return state;
    }).then(() => {
      inFlight = null;
      if (refreshAgain) {
        refreshAgain = false;
        const background = nextBackground;
        nextBackground = true;
        return refresh({ background });
      }
      return state;
    });
    return inFlight;
  };
  return {
    getSnapshot: () => state,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    refresh,
    invalidate: ({ background = false } = {}) => {
      revision++;
      if (!background || !['available', 'locked'].includes(state.status)) {
        publish({ ...state, status: 'checking', error: null });
      }
      if (inFlight) {
        refreshAgain = true;
        nextBackground = nextBackground && background;
      } else refresh({ background });
    },
    reportLocked: (body) => {
      revision++;
      publish({ status: 'locked', examType: body.exam_type || null, error: null });
    },
  };
}
