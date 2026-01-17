-- Sindri UI
-- Floating windows and output display for Neovim

local M = {}

-- State
M._state = {
  float_win = nil,
  float_buf = nil,
  loading_win = nil,
  loading_buf = nil,
  loading_timer = nil,
  progress = 0,
  output_lines = {},
}

-- Get config from parent
local function get_config()
  return require("sindri").config.ui.float
end

-- Create a floating window
function M.create_float(opts)
  opts = opts or {}
  local config = get_config()

  local width = opts.width or config.width
  local height = opts.height or config.height
  local border = opts.border or config.border
  local title = opts.title or config.title

  -- Calculate position
  local ui_width = vim.o.columns
  local ui_height = vim.o.lines
  local row = math.floor((ui_height - height) / 2)
  local col = math.floor((ui_width - width) / 2)

  -- Create buffer
  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].filetype = opts.filetype or "markdown"

  -- Create window
  local win_opts = {
    relative = "editor",
    width = width,
    height = height,
    row = row,
    col = col,
    style = "minimal",
    border = border,
    title = title,
    title_pos = "center",
  }

  local win = vim.api.nvim_open_win(buf, true, win_opts)

  -- Set window options
  vim.wo[win].wrap = true
  vim.wo[win].linebreak = true
  vim.wo[win].cursorline = false
  vim.wo[win].number = false

  -- Set up keymaps to close
  vim.keymap.set("n", "q", function()
    if vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_win_close(win, true)
    end
  end, { buffer = buf, nowait = true })

  vim.keymap.set("n", "<Esc>", function()
    if vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_win_close(win, true)
    end
  end, { buffer = buf, nowait = true })

  return win, buf
end

-- Show simple result in float
function M.show_result(title, lines)
  local win, buf = M.create_float({ title = " " .. title .. " " })

  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false

  M._state.float_win = win
  M._state.float_buf = buf
end

-- Show markdown content in float
function M.show_markdown(title, content, opts)
  opts = opts or {}
  local win, buf = M.create_float({
    title = " " .. title .. " ",
    filetype = "markdown",
  })

  -- Parse markdown and set lines
  local lines = vim.split(content, "\n")
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)

  -- Add action keymaps if provided
  if opts.apply_action then
    vim.keymap.set("n", "<CR>", function()
      -- Extract code blocks and apply
      local code = M._extract_code_block(lines)
      if code then
        opts.apply_action(code)
        vim.api.nvim_win_close(win, true)
      else
        vim.notify("No code block found", vim.log.levels.WARN)
      end
    end, { buffer = buf, desc = "Apply code" })

    -- Add hint
    table.insert(lines, "")
    table.insert(lines, "---")
    table.insert(lines, "_Press Enter to apply, q to close_")
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  end

  vim.bo[buf].modifiable = false

  M._state.float_win = win
  M._state.float_buf = buf
end

-- Extract code block from markdown lines
function M._extract_code_block(lines)
  local in_code = false
  local code_lines = {}

  for _, line in ipairs(lines) do
    if line:match("^```") then
      if in_code then
        -- End of code block
        break
      else
        -- Start of code block
        in_code = true
      end
    elseif in_code then
      table.insert(code_lines, line)
    end
  end

  if #code_lines > 0 then
    return table.concat(code_lines, "\n")
  end
  return nil
end

-- Show loading indicator
function M.show_loading(message)
  message = message or "Loading..."

  -- Close existing loading window
  M.hide_loading()

  local config = get_config()
  local width = math.min(40, #message + 10)
  local height = 3

  local ui_width = vim.o.columns
  local ui_height = vim.o.lines
  local row = math.floor((ui_height - height) / 2)
  local col = math.floor((ui_width - width) / 2)

  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].bufhidden = "wipe"

  local win = vim.api.nvim_open_win(buf, false, {
    relative = "editor",
    width = width,
    height = height,
    row = row,
    col = col,
    style = "minimal",
    border = config.border,
    title = " Sindri ",
    title_pos = "center",
  })

  -- Animation frames
  local frames = { "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏" }
  local frame_index = 1

  -- Update function
  local function update()
    if not vim.api.nvim_win_is_valid(win) then
      return
    end

    local spinner = frames[frame_index]
    local lines = {
      "",
      string.format("  %s %s", spinner, message),
      "",
    }
    vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)

    frame_index = (frame_index % #frames) + 1
  end

  -- Initial update
  update()

  -- Start animation timer
  M._state.loading_timer = vim.loop.new_timer()
  M._state.loading_timer:start(0, 100, vim.schedule_wrap(update))

  M._state.loading_win = win
  M._state.loading_buf = buf
end

-- Hide loading indicator
function M.hide_loading()
  if M._state.loading_timer then
    M._state.loading_timer:stop()
    M._state.loading_timer:close()
    M._state.loading_timer = nil
  end

  if M._state.loading_win and vim.api.nvim_win_is_valid(M._state.loading_win) then
    vim.api.nvim_win_close(M._state.loading_win, true)
  end

  M._state.loading_win = nil
  M._state.loading_buf = nil
end

-- Update progress display
function M.update_progress(progress, status, message)
  M._state.progress = progress

  if not M._state.loading_win or not vim.api.nvim_win_is_valid(M._state.loading_win) then
    M.show_loading(message)
    return
  end

  -- Update loading message with progress
  local progress_bar = M._make_progress_bar(progress, 20)
  local lines = {
    "",
    string.format("  %s %s", status, message),
    string.format("  %s %.0f%%", progress_bar, progress * 100),
  }

  vim.api.nvim_buf_set_lines(M._state.loading_buf, 0, -1, false, lines)
end

-- Create progress bar string
function M._make_progress_bar(progress, width)
  local filled = math.floor(progress * width)
  local empty = width - filled
  return "[" .. string.rep("=", filled) .. string.rep(" ", empty) .. "]"
end

-- Append output to float (for streaming)
function M.append_output(text)
  if not M._state.float_win or not vim.api.nvim_win_is_valid(M._state.float_win) then
    -- Create output window if not exists
    local win, buf = M.create_float({ title = " Output " })
    M._state.float_win = win
    M._state.float_buf = buf
    M._state.output_lines = {}
  end

  -- Append lines
  local new_lines = vim.split(text, "\n")
  for _, line in ipairs(new_lines) do
    table.insert(M._state.output_lines, line)
  end

  vim.bo[M._state.float_buf].modifiable = true
  vim.api.nvim_buf_set_lines(M._state.float_buf, 0, -1, false, M._state.output_lines)
  vim.bo[M._state.float_buf].modifiable = false

  -- Scroll to bottom
  local line_count = #M._state.output_lines
  vim.api.nvim_win_set_cursor(M._state.float_win, { line_count, 0 })
end

-- Append streaming token
function M.append_token(token)
  if not M._state.float_win or not vim.api.nvim_win_is_valid(M._state.float_win) then
    -- Create output window if not exists
    local win, buf = M.create_float({ title = " Output " })
    M._state.float_win = win
    M._state.float_buf = buf
    M._state.output_lines = { "" }
  end

  -- Append token to last line
  local last_idx = #M._state.output_lines
  if last_idx == 0 then
    M._state.output_lines = { "" }
    last_idx = 1
  end

  -- Handle newlines in token
  local parts = vim.split(token, "\n", { plain = true })
  for i, part in ipairs(parts) do
    if i == 1 then
      M._state.output_lines[last_idx] = M._state.output_lines[last_idx] .. part
    else
      table.insert(M._state.output_lines, part)
      last_idx = last_idx + 1
    end
  end

  vim.bo[M._state.float_buf].modifiable = true
  vim.api.nvim_buf_set_lines(M._state.float_buf, 0, -1, false, M._state.output_lines)
  vim.bo[M._state.float_buf].modifiable = false

  -- Scroll to bottom
  local line_count = #M._state.output_lines
  vim.api.nvim_win_set_cursor(M._state.float_win, { line_count, 0 })
end

-- Close all UI elements
function M.close_all()
  M.hide_loading()

  if M._state.float_win and vim.api.nvim_win_is_valid(M._state.float_win) then
    vim.api.nvim_win_close(M._state.float_win, true)
  end

  M._state.float_win = nil
  M._state.float_buf = nil
  M._state.output_lines = {}
end

return M
