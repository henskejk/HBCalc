// A pint glass filled with beer of the given color.
export default function Glass({ hex, label, width = 40, height = 55 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 24 34" role="img" aria-label={`Beer color: ${label}`}>
      <title>{label}</title>
      <path d="M2.48 7 L21.52 7 L19.5 32 Q19.4 33 18.4 33 L5.6 33 Q4.6 33 4.5 32 Z" fill={hex} />
      <path d="M2.12 2.5 L21.88 2.5 L21.52 7 L2.48 7 Z" fill="#FFF8E7" />
      <g fill="#FFF8E7">
        <circle cx="4.2" cy="2.6" r="1.6" />
        <circle cx="7.6" cy="2.1" r="1.8" />
        <circle cx="11.2" cy="2.5" r="1.7" />
        <circle cx="14.8" cy="2.0" r="1.8" />
        <circle cx="18.2" cy="2.4" r="1.7" />
        <circle cx="20.4" cy="2.8" r="1.4" />
      </g>
      <path d="M5 9 L6.6 30" stroke="#fff" strokeOpacity=".35" strokeWidth="1.1" strokeLinecap="round" />
      <path
        d="M2 1 L22 1 L19.5 32 Q19.4 33 18.4 33 L5.6 33 Q4.6 33 4.5 32 Z"
        fill="none"
        stroke="rgba(128,128,128,.7)"
        strokeWidth=".9"
        strokeLinejoin="round"
      />
    </svg>
  );
}
