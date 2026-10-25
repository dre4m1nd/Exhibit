#!/usr/bin/env node
/** Exhibit's terminal entrypoint. */

import React from "react";
import { render } from "ink";
import { App } from "./components/App.js";

const model = process.env.EXHIBIT_MODEL ?? "gpt-5.4-mini";

render(<App model={model} />);
