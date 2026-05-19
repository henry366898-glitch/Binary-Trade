// Centralised lead-capture CTAs. One academy (Stewarts), one WhatsApp number,
// different pre-filled messages per surface so sales sees where the lead came from.

const WA_NUMBER = '971544411336';

const MESSAGES = {
  modal_low:    'Hi, I want to book a free consultation for Stewarts Academy',
  modal_zero:   'Hi, I want to book a free consultation for Stewarts Academy',
  nudge_streak: 'Hi, I would like a free 15-min consultation with Stewarts Academy',
  toast:        'Hi, I would like training info from Stewarts Academy',
  footer:       'Hi, I would like to book a free call with Stewarts Academy',
};

export function waLink(surface) {
  const msg = MESSAGES[surface] || MESSAGES.footer;
  return `https://wa.me/${WA_NUMBER}?text=${encodeURIComponent(msg)}`;
}

export function logAcademyClick(surface, academy = 'stewarts') {
  // fire-and-forget — don't block the WhatsApp open
  fetch('/api/leads/academy_click', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
    body: JSON.stringify({ academy_name: academy, surface }),
  }).catch(() => {});
}

export function openAcademyCta(surface) {
  logAcademyClick(surface);
  window.open(waLink(surface), '_blank', 'noopener,noreferrer');
}
