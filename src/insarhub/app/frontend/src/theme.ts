export interface Theme {
  isDark:        boolean
  bg:            string   // main bar background
  bg2:           string   // secondary toolbar background
  border:        string
  text:          string   // primary text
  textMuted:     string   // secondary labels
  inputBg:       string
  inputBorder:   string
  btnActiveBg:   string
  btnActiveFg:   string
  btnActiveBorder: string
  divider:       string
  accent:        string
}

export const DARK: Theme = {
  isDark:          true,
  bg:              '#1a1a2e',
  bg2:             '#12121f',
  border:          '#2a2a4e',
  text:            '#e0e0e0',
  textMuted:       '#aaa',
  inputBg:         '#0d0d1a',
  inputBorder:     '#2a2a4e',
  btnActiveBg:     '#1a5276',
  btnActiveFg:     '#4fc3f7',
  btnActiveBorder: '#2e86c1',
  divider:         '#2a2a4e',
  accent:          '#4fc3f7',
}

export const LIGHT: Theme = {
  isDark:          false,
  bg:              '#e8ecf0',      // light top bar
  bg2:             '#f0f2f5',
  border:          '#c8cdd4',
  text:            '#1a1a2e',
  textMuted:       '#555',
  inputBg:         '#ffffff',
  inputBorder:     '#bbb',
  btnActiveBg:     '#d6eaf8',
  btnActiveFg:     '#1a5276',
  btnActiveBorder: '#2e86c1',
  divider:         '#c8cdd4',
  accent:          '#2e86c1',
}