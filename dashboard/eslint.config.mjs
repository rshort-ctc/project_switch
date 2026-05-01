import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  {
    ignores: ["src-tauri/gen/**", "src-tauri/target/**"],
  },
  ...nextVitals,
];

export default eslintConfig;
