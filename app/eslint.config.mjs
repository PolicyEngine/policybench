import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

const config = [
  {
    ignores: [".next/**", "dist/**", "node_modules/**", "out/**"],
  },
  ...nextCoreWebVitals,
  ...nextTypeScript,
];

export default config;
