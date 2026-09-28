/**
 * Springs for WAAPI, without a motion library.
 *
 * A damped spring is simulated once and sampled into a CSS `linear()`
 * easing, so the browser runs it like any other animation (off the main
 * thread for transform/opacity). Parameters follow Apple's model: how long
 * it takes to settle, and how much it bounces (0 = critically damped).
 * `velocity` is the starting speed as a fraction of the distance per second,
 * which is how a flick hands its momentum to the settle.
 */
export function springEasing({
  duration = 0.5,
  bounce = 0.2,
  velocity = 0,
}: {
  duration?: number;
  bounce?: number;
  velocity?: number;
} = {}): { easing: string; duration: number } {
  const omega = (2 * Math.PI) / duration;
  const zeta = 1 - bounce;
  const dt = 1 / 240;
  let x = 0;
  let v = velocity;
  const samples: number[] = [0];
  let t = 0;
  let settledFor = 0;
  // Integrate until it's been at rest for a moment (cap at 2s).
  while (t < 2) {
    const a = -omega * omega * (x - 1) - 2 * zeta * omega * v;
    v += a * dt;
    x += v * dt;
    t += dt;
    if (Math.round(t / dt) % 4 === 0) samples.push(x);
    settledFor = Math.abs(x - 1) < 0.001 && Math.abs(v) < 0.01 ? settledFor + dt : 0;
    if (settledFor > 0.05) break;
  }
  samples[samples.length - 1] = 1;
  return {
    easing: `linear(${samples.map((s) => +s.toFixed(4)).join(", ")})`,
    duration: Math.round(t * 1000),
  };
}
