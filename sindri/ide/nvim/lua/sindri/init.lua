-- Sindri Neovim Plugin
-- Local-first LLM orchestration for code assistance

local M = {}

-- Configuration defaults
M.config = {
  -- Server settings
  server = {
    -- Path to sindri executable (auto-detect if nil)
    executable = nil,
    -- Working directory (defaults to cwd)
    work_dir = nil,
    -- Auto-start server when needed
    auto_start = true,
  },

  -- UI settings
  ui = {
    -- Float window settings
    float = {
      width = 80,
      height = 20,
      border = "rounded",
      title = " Sindri ",
    },
    -- Output format
    format = "markdown",
  },

  -- Agent settings
  agent = {
    -- Default agent for tasks
    default = "brokkr",
    -- Max iterations
    max_iterations = 30,
    -- Enable memory
    enable_memory = true,
  },

  -- Keymaps (set to false to disable)
  keymaps = {
    -- Run task on selection
    run_selection = "<leader>sr",
    -- Explain code
    explain = "<leader>se",
    -- Suggest fix for error
    fix = "<leader>sf",
    -- Generate tests
    tests = "<leader>st",
    -- Refactor code
    refactor = "<leader>sR",
    -- Cancel running task
    cancel = "<leader>sc",
    -- Show task status
    status = "<leader>ss",
    -- List agents
    agents = "<leader>sa",
  },
}

-- Server state
M._server = {
  job_id = nil,
  started = false,
  request_id = 0,
  pending_requests = {},
  buffer = "",
}

-- Client module
local client = require("sindri.client")
local ui = require("sindri.ui")

-- Setup function
function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})

  -- Set up keymaps
  if M.config.keymaps then
    M._setup_keymaps()
  end

  -- Set up user commands
  M._setup_commands()

  -- Auto-detect sindri executable
  if not M.config.server.executable then
    M.config.server.executable = M._find_executable()
  end
end

-- Find sindri executable
function M._find_executable()
  -- Check common locations
  local paths = {
    vim.fn.expand("~/.local/bin/sindri"),
    vim.fn.expand("~/.sindri/venv/bin/sindri"),
    "/usr/local/bin/sindri",
    -- Check if in a project with venv
    vim.fn.getcwd() .. "/.venv/bin/sindri",
  }

  for _, path in ipairs(paths) do
    if vim.fn.executable(path) == 1 then
      return path
    end
  end

  -- Fall back to PATH
  if vim.fn.executable("sindri") == 1 then
    return "sindri"
  end

  return nil
end

-- Setup keymaps
function M._setup_keymaps()
  local km = M.config.keymaps

  if km.run_selection then
    vim.keymap.set("v", km.run_selection, function()
      M.run_selection()
    end, { desc = "Sindri: Run task on selection" })
  end

  if km.explain then
    vim.keymap.set({ "n", "v" }, km.explain, function()
      M.explain_code()
    end, { desc = "Sindri: Explain code" })
  end

  if km.fix then
    vim.keymap.set({ "n", "v" }, km.fix, function()
      M.suggest_fix()
    end, { desc = "Sindri: Suggest fix" })
  end

  if km.tests then
    vim.keymap.set({ "n", "v" }, km.tests, function()
      M.generate_tests()
    end, { desc = "Sindri: Generate tests" })
  end

  if km.refactor then
    vim.keymap.set("v", km.refactor, function()
      M.refactor_code()
    end, { desc = "Sindri: Refactor code" })
  end

  if km.cancel then
    vim.keymap.set("n", km.cancel, function()
      M.cancel_task()
    end, { desc = "Sindri: Cancel task" })
  end

  if km.status then
    vim.keymap.set("n", km.status, function()
      M.show_status()
    end, { desc = "Sindri: Show status" })
  end

  if km.agents then
    vim.keymap.set("n", km.agents, function()
      M.list_agents()
    end, { desc = "Sindri: List agents" })
  end
end

-- Setup user commands
function M._setup_commands()
  vim.api.nvim_create_user_command("Sindri", function(opts)
    local args = opts.fargs
    if #args == 0 then
      M.show_menu()
      return
    end

    local cmd = args[1]
    local rest = table.concat(vim.list_slice(args, 2), " ")

    if cmd == "run" then
      M.run_task(rest)
    elseif cmd == "explain" then
      M.explain_code()
    elseif cmd == "fix" then
      M.suggest_fix()
    elseif cmd == "tests" then
      M.generate_tests()
    elseif cmd == "refactor" then
      M.refactor_code(rest)
    elseif cmd == "cancel" then
      M.cancel_task()
    elseif cmd == "status" then
      M.show_status()
    elseif cmd == "agents" then
      M.list_agents()
    elseif cmd == "sessions" then
      M.list_sessions()
    elseif cmd == "start" then
      M.start_server()
    elseif cmd == "stop" then
      M.stop_server()
    else
      vim.notify("Unknown Sindri command: " .. cmd, vim.log.levels.ERROR)
    end
  end, {
    nargs = "*",
    complete = function(_, line)
      local cmds = {
        "run",
        "explain",
        "fix",
        "tests",
        "refactor",
        "cancel",
        "status",
        "agents",
        "sessions",
        "start",
        "stop",
      }
      local l = vim.split(line, "%s+")
      if #l == 2 then
        return vim.tbl_filter(function(val)
          return vim.startswith(val, l[2])
        end, cmds)
      end
      return cmds
    end,
    desc = "Sindri commands",
  })

  -- Shortcut commands
  vim.api.nvim_create_user_command("SindriRun", function(opts)
    M.run_task(opts.args)
  end, { nargs = "+", desc = "Run Sindri task" })

  vim.api.nvim_create_user_command("SindriExplain", function()
    M.explain_code()
  end, { range = true, desc = "Explain code with Sindri" })

  vim.api.nvim_create_user_command("SindriFix", function()
    M.suggest_fix()
  end, { range = true, desc = "Suggest fix with Sindri" })

  vim.api.nvim_create_user_command("SindriTests", function()
    M.generate_tests()
  end, { range = true, desc = "Generate tests with Sindri" })
end

-- Start the IDE server
function M.start_server()
  if M._server.started then
    vim.notify("Sindri server already running", vim.log.levels.INFO)
    return
  end

  local executable = M.config.server.executable
  if not executable then
    vim.notify("Sindri executable not found", vim.log.levels.ERROR)
    return
  end

  local args = { executable, "ide", "--mode", "stdio" }
  if M.config.server.work_dir then
    table.insert(args, "--work-dir")
    table.insert(args, M.config.server.work_dir)
  end

  M._server.job_id = vim.fn.jobstart(args, {
    on_stdout = function(_, data)
      client.handle_data(data)
    end,
    on_stderr = function(_, data)
      for _, line in ipairs(data) do
        if line ~= "" then
          vim.notify("Sindri: " .. line, vim.log.levels.WARN)
        end
      end
    end,
    on_exit = function(_, code)
      M._server.started = false
      M._server.job_id = nil
      if code ~= 0 then
        vim.notify("Sindri server exited with code " .. code, vim.log.levels.ERROR)
      end
    end,
  })

  if M._server.job_id > 0 then
    M._server.started = true
    -- Send initialize request
    client.initialize(M.config)
    vim.notify("Sindri server started", vim.log.levels.INFO)
  else
    vim.notify("Failed to start Sindri server", vim.log.levels.ERROR)
  end
end

-- Stop the IDE server
function M.stop_server()
  if not M._server.started then
    vim.notify("Sindri server not running", vim.log.levels.INFO)
    return
  end

  client.shutdown()

  if M._server.job_id then
    vim.fn.jobstop(M._server.job_id)
    M._server.job_id = nil
  end

  M._server.started = false
  vim.notify("Sindri server stopped", vim.log.levels.INFO)
end

-- Ensure server is running
function M._ensure_server()
  if not M._server.started and M.config.server.auto_start then
    M.start_server()
    -- Wait a bit for initialization
    vim.wait(500, function()
      return client.is_initialized()
    end, 50)
  end

  return M._server.started
end

-- Get current file info
function M._get_file_info()
  local bufnr = vim.api.nvim_get_current_buf()
  local file_path = vim.api.nvim_buf_get_name(bufnr)
  local filetype = vim.bo[bufnr].filetype

  return {
    path = file_path,
    language = filetype,
    bufnr = bufnr,
  }
end

-- Get visual selection
function M._get_selection()
  local mode = vim.fn.mode()
  if mode ~= "v" and mode ~= "V" and mode ~= "\22" then
    -- Not in visual mode, get current line
    local line = vim.api.nvim_get_current_line()
    return line
  end

  -- Get visual selection
  local start_pos = vim.fn.getpos("'<")
  local end_pos = vim.fn.getpos("'>")
  local lines = vim.api.nvim_buf_get_lines(
    0,
    start_pos[2] - 1,
    end_pos[2],
    false
  )

  if #lines == 0 then
    return ""
  end

  -- Adjust for partial line selection
  if #lines == 1 then
    lines[1] = string.sub(lines[1], start_pos[3], end_pos[3])
  else
    lines[1] = string.sub(lines[1], start_pos[3])
    lines[#lines] = string.sub(lines[#lines], 1, end_pos[3])
  end

  return table.concat(lines, "\n")
end

-- Run a task
function M.run_task(description)
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  local file_info = M._get_file_info()

  client.execute_task({
    description = description,
    agent = M.config.agent.default,
    max_iterations = M.config.agent.max_iterations,
    enable_memory = M.config.agent.enable_memory,
    current_file = file_info.path,
  }, function(result)
    if result.error then
      vim.notify("Task failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      ui.show_result("Task Started", {
        "Task ID: " .. result.taskId,
        "Status: " .. result.status,
        result.message,
      })
    end
  end)
end

-- Run task on visual selection
function M.run_selection()
  local selection = M._get_selection()
  if selection == "" then
    vim.notify("No selection", vim.log.levels.WARN)
    return
  end

  vim.ui.input({ prompt = "Sindri task: " }, function(input)
    if input and input ~= "" then
      M.run_task(input .. "\n\nCode:\n```\n" .. selection .. "\n```")
    end
  end)
end

-- Explain code
function M.explain_code()
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  local selection = M._get_selection()
  local file_info = M._get_file_info()

  if selection == "" then
    vim.notify("No code selected", vim.log.levels.WARN)
    return
  end

  ui.show_loading("Explaining code...")

  client.explain_code({
    code = selection,
    language = file_info.language,
    file_path = file_info.path,
    detail_level = "normal",
  }, function(result)
    ui.hide_loading()
    if result.error then
      vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      ui.show_markdown("Code Explanation", result.explanation)
    end
  end)
end

-- Suggest fix for error
function M.suggest_fix()
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  local selection = M._get_selection()
  local file_info = M._get_file_info()

  -- Get diagnostics for current position
  local diagnostics = vim.diagnostic.get(0, { lnum = vim.fn.line(".") - 1 })
  local error_message = ""
  if #diagnostics > 0 then
    error_message = diagnostics[1].message
  end

  if selection == "" then
    -- Get whole function or current line
    selection = vim.api.nvim_get_current_line()
  end

  vim.ui.input({
    prompt = "Error message: ",
    default = error_message,
  }, function(input)
    if not input then
      return
    end

    ui.show_loading("Finding fix...")

    client.suggest_fix({
      code = selection,
      error_message = input,
      language = file_info.language,
      file_path = file_info.path,
    }, function(result)
      ui.hide_loading()
      if result.error then
        vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
      else
        ui.show_markdown("Suggested Fix", result.suggestion)
      end
    end)
  end)
end

-- Generate tests
function M.generate_tests()
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  local selection = M._get_selection()
  local file_info = M._get_file_info()

  if selection == "" then
    vim.notify("No code selected", vim.log.levels.WARN)
    return
  end

  ui.show_loading("Generating tests...")

  client.generate_tests({
    code = selection,
    language = file_info.language,
    file_path = file_info.path,
  }, function(result)
    ui.hide_loading()
    if result.error then
      vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      ui.show_markdown("Generated Tests", result.tests, {
        apply_action = function(content)
          -- Create new buffer with tests
          vim.cmd("vnew")
          local bufnr = vim.api.nvim_get_current_buf()
          vim.api.nvim_buf_set_lines(bufnr, 0, -1, false, vim.split(content, "\n"))
          vim.bo[bufnr].filetype = file_info.language
        end,
      })
    end
  end)
end

-- Refactor code
function M.refactor_code(refactor_type)
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  local selection = M._get_selection()
  local file_info = M._get_file_info()

  if selection == "" then
    vim.notify("No code selected", vim.log.levels.WARN)
    return
  end

  local refactor_types = {
    "extract_function",
    "extract_variable",
    "inline",
    "rename",
    "simplify",
    "optimize",
  }

  if not refactor_type or refactor_type == "" then
    vim.ui.select(refactor_types, { prompt = "Refactor type:" }, function(choice)
      if choice then
        M._do_refactor(selection, file_info, choice)
      end
    end)
  else
    M._do_refactor(selection, file_info, refactor_type)
  end
end

function M._do_refactor(code, file_info, refactor_type)
  ui.show_loading("Refactoring code...")

  client.refactor_code({
    code = code,
    refactor_type = refactor_type,
    language = file_info.language,
    file_path = file_info.path,
  }, function(result)
    ui.hide_loading()
    if result.error then
      vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      ui.show_markdown("Refactored Code", result.refactored, {
        apply_action = function(content)
          -- Replace selection with refactored code
          local start_pos = vim.fn.getpos("'<")
          local end_pos = vim.fn.getpos("'>")
          vim.api.nvim_buf_set_lines(
            0,
            start_pos[2] - 1,
            end_pos[2],
            false,
            vim.split(content, "\n")
          )
        end,
      })
    end
  end)
end

-- Cancel current task
function M.cancel_task()
  if not M._server.started then
    vim.notify("Sindri server not running", vim.log.levels.INFO)
    return
  end

  local task_id = client.get_current_task_id()
  if not task_id then
    vim.notify("No active task", vim.log.levels.INFO)
    return
  end

  client.cancel_task(task_id, function(result)
    if result.error then
      vim.notify("Cancel failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      vim.notify("Task cancelled", vim.log.levels.INFO)
    end
  end)
end

-- Show task status
function M.show_status()
  if not M._server.started then
    vim.notify("Sindri server not running", vim.log.levels.INFO)
    return
  end

  local task_id = client.get_current_task_id()
  if not task_id then
    ui.show_result("Status", { "No active task", "", "Server: running" })
    return
  end

  client.get_task_status(task_id, function(result)
    if result.error then
      vim.notify("Status failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      ui.show_result("Task Status", {
        "Task ID: " .. result.taskId,
        "Status: " .. result.status,
        result.result or result.error or "",
      })
    end
  end)
end

-- List agents
function M.list_agents()
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  client.list_agents(function(result)
    if result.error then
      vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      local lines = { "# Sindri Agents", "" }
      for _, agent in ipairs(result.agents) do
        table.insert(lines, string.format("## %s", agent.name))
        table.insert(lines, string.format("**Role:** %s", agent.role))
        table.insert(lines, string.format("**Model:** %s", agent.model))
        table.insert(lines, string.format("**Tools:** %d", #agent.tools))
        table.insert(lines, "")
      end
      ui.show_markdown("Agents", table.concat(lines, "\n"))
    end
  end)
end

-- List sessions
function M.list_sessions()
  if not M._ensure_server() then
    vim.notify("Sindri server not available", vim.log.levels.ERROR)
    return
  end

  client.list_sessions({ limit = 10 }, function(result)
    if result.error then
      vim.notify("Failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      local lines = { "# Recent Sessions", "" }
      for _, session in ipairs(result.sessions) do
        table.insert(
          lines,
          string.format("- **%s** - %s", session.id:sub(1, 8), session.task:sub(1, 50))
        )
      end
      if #result.sessions == 0 then
        table.insert(lines, "_No sessions found_")
      end
      ui.show_markdown("Sessions", table.concat(lines, "\n"))
    end
  end)
end

-- Show interactive menu
function M.show_menu()
  local items = {
    { label = "Run task", action = function()
      vim.ui.input({ prompt = "Task: " }, function(input)
        if input then
          M.run_task(input)
        end
      end)
    end },
    { label = "Explain code", action = M.explain_code },
    { label = "Suggest fix", action = M.suggest_fix },
    { label = "Generate tests", action = M.generate_tests },
    { label = "Refactor code", action = M.refactor_code },
    { label = "List agents", action = M.list_agents },
    { label = "List sessions", action = M.list_sessions },
    { label = "Show status", action = M.show_status },
    { label = "Cancel task", action = M.cancel_task },
    { label = "Start server", action = M.start_server },
    { label = "Stop server", action = M.stop_server },
  }

  vim.ui.select(items, {
    prompt = "Sindri:",
    format_item = function(item)
      return item.label
    end,
  }, function(choice)
    if choice then
      choice.action()
    end
  end)
end

return M
