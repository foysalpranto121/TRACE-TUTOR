// Assessment changes invalidate eligibility; only a fresh response for the same
// authenticated session may update it. Overlapping signals share one request and
// schedule one follow-up when an event arrives during that request.
export function createProfileRefresh({ readIdentity, fetchProfile, applyProfile, expireSession }) {
  let revision = 0;
  let active = false;
  let inFlight = null;
  let queued = false;
  const matches = (identity) => {
    const current = readIdentity();
    return current && current.id === identity.id && current.token === identity.token;
  };
  const refresh = ({ invalidate = false } = {}) => {
    if (invalidate) revision++;
    if (!active) return Promise.resolve(null);
    if (inFlight) {
      queued = true;
      return inFlight;
    }
    const identity = readIdentity();
    if (!identity) return Promise.resolve(null);
    const started = revision;
    const current = () => active && revision === started && matches(identity);
    inFlight = Promise.resolve().then(fetchProfile).then((fresh) => {
      if (current() && fresh?.id === identity.id && typeof fresh.arm_self_select === 'boolean') {
        applyProfile(fresh);
        return fresh;
      }
      return null;
    }).catch((error) => {
      if (current() && error.status === 401) expireSession();
      return null;
    }).then((result) => {
      inFlight = null;
      if (queued && active) {
        queued = false;
        return refresh();
      }
      return result;
    });
    return inFlight;
  };
  return {
    refresh,
    invalidate: () => { revision++; },
    start: () => { active = true; },
    stop: () => { active = false; queued = false; revision++; },
  };
}
