-- Sindri Client
-- JSON-RPC client for communicating with Sindri IDE server

local M = {}

-- State
M._state = {
  initialized = false,
  request_id = 0,
  pending_requests = {},
  current_task_id = nil,
  buffer = "",
}

-- Get parent module for job access
local function get_parent()
  return require("sindri")
end

-- Generate next request ID
local function next_id()
  M._state.request_id = M._state.request_id + 1
  return M._state.request_id
end

-- Send a JSON-RPC message
function M.send(message)
  local parent = get_parent()
  if not parent._server.job_id then
    vim.notify("Sindri server not running", vim.log.levels.ERROR)
    return false
  end

  local content = vim.fn.json_encode(message)
  local header = string.format("Content-Length: %d\r\n\r\n", #content)
  local data = header .. content

  vim.fn.chansend(parent._server.job_id, data)
  return true
end

-- Send a request and wait for response
function M.request(method, params, callback)
  local id = next_id()

  local message = {
    jsonrpc = "2.0",
    id = id,
    method = method,
  }

  if params then
    message.params = params
  end

  M._state.pending_requests[id] = callback

  if not M.send(message) then
    M._state.pending_requests[id] = nil
    callback({ error = { code = -1, message = "Server not running" } })
  end
end

-- Send a notification (no response expected)
function M.notify(method, params)
  local message = {
    jsonrpc = "2.0",
    method = method,
  }

  if params then
    message.params = params
  end

  M.send(message)
end

-- Handle incoming data from server
function M.handle_data(data)
  -- Append to buffer
  for _, chunk in ipairs(data) do
    if chunk ~= "" then
      M._state.buffer = M._state.buffer .. chunk
    end
  end

  -- Parse messages from buffer
  while true do
    local message = M._parse_message()
    if not message then
      break
    end
    M._handle_message(message)
  end
end

-- Parse a single message from buffer
function M._parse_message()
  -- Look for Content-Length header
  local header_end = M._state.buffer:find("\r\n\r\n")
  if not header_end then
    return nil
  end

  local header = M._state.buffer:sub(1, header_end - 1)
  local content_length = header:match("Content%-Length:%s*(%d+)")
  if not content_length then
    -- Invalid header, try to recover
    M._state.buffer = M._state.buffer:sub(header_end + 4)
    return nil
  end

  content_length = tonumber(content_length)
  local content_start = header_end + 4
  local content_end = content_start + content_length - 1

  if #M._state.buffer < content_end then
    -- Not enough data yet
    return nil
  end

  local content = M._state.buffer:sub(content_start, content_end)
  M._state.buffer = M._state.buffer:sub(content_end + 1)

  local ok, message = pcall(vim.fn.json_decode, content)
  if ok then
    return message
  else
    vim.notify("Failed to parse JSON: " .. content:sub(1, 100), vim.log.levels.WARN)
    return nil
  end
end

-- Handle a parsed message
function M._handle_message(message)
  -- Check if it's a response to a request
  if message.id then
    local callback = M._state.pending_requests[message.id]
    if callback then
      M._state.pending_requests[message.id] = nil
      vim.schedule(function()
        if message.error then
          callback({ error = message.error })
        else
          callback(message.result or {})
        end
      end)
    end
    return
  end

  -- It's a notification
  if message.method then
    M._handle_notification(message)
  end
end

-- Handle server notifications
function M._handle_notification(notification)
  local method = notification.method
  local params = notification.params or {}

  if method == "sindri/logMessage" then
    local level = vim.log.levels[params.level:upper()] or vim.log.levels.INFO
    vim.notify("Sindri: " .. params.message, level)
  elseif method == "sindri/taskProgress" then
    M._handle_task_progress(params)
  elseif method == "sindri/taskOutput" then
    M._handle_task_output(params)
  elseif method == "sindri/taskComplete" then
    M._handle_task_complete(params)
  elseif method == "sindri/streamingToken" then
    M._handle_streaming_token(params)
  end
end

-- Handle task progress notification
function M._handle_task_progress(params)
  local ui = require("sindri.ui")
  local progress = params.progress or 0
  local status = params.status or "running"
  local message = params.message or ""

  ui.update_progress(progress, status, message)
end

-- Handle task output notification
function M._handle_task_output(params)
  local ui = require("sindri.ui")
  ui.append_output(params.output or "")
end

-- Handle task complete notification
function M._handle_task_complete(params)
  M._state.current_task_id = nil
  local ui = require("sindri.ui")
  ui.hide_loading()

  if params.success then
    vim.notify("Task completed successfully", vim.log.levels.INFO)
  else
    vim.notify("Task failed: " .. (params.error or "Unknown error"), vim.log.levels.ERROR)
  end
end

-- Handle streaming token notification
function M._handle_streaming_token(params)
  local ui = require("sindri.ui")
  ui.append_token(params.token or "")

  if params.isComplete then
    M._state.current_task_id = nil
  end
end

-- Check if initialized
function M.is_initialized()
  return M._state.initialized
end

-- Get current task ID
function M.get_current_task_id()
  return M._state.current_task_id
end

-- Initialize connection
function M.initialize(config)
  local params = {
    processId = vim.fn.getpid(),
    clientInfo = {
      name = "neovim-sindri",
      version = "0.1.0",
    },
    capabilities = {
      textDocumentSync = true,
      streaming = true,
      showMessage = true,
      logMessage = true,
      workspaceFolders = true,
    },
    workspaceFolders = { vim.fn.getcwd() },
  }

  if config.server.work_dir then
    params.workspaceFolders = { config.server.work_dir }
  end

  M.request("initialize", params, function(result)
    if result.error then
      vim.notify("Initialize failed: " .. result.error.message, vim.log.levels.ERROR)
    else
      M._state.initialized = true
      vim.notify("Sindri initialized", vim.log.levels.INFO)
    end
  end)
end

-- Shutdown connection
function M.shutdown()
  M.request("shutdown", nil, function()
    M._state.initialized = false
  end)
end

-- Execute task
function M.execute_task(params, callback)
  local req_params = {
    description = params.description,
    agent = params.agent or "brokkr",
    maxIterations = params.max_iterations or 30,
    enableMemory = params.enable_memory ~= false,
    currentFile = params.current_file,
    currentSelection = params.current_selection,
  }

  if params.work_dir then
    req_params.workDir = params.work_dir
  end

  M.request("sindri/executeTask", req_params, function(result)
    if result.taskId then
      M._state.current_task_id = result.taskId
    end
    callback(result)
  end)
end

-- Cancel task
function M.cancel_task(task_id, callback)
  M.request("sindri/cancelTask", { taskId = task_id }, callback)
end

-- Get task status
function M.get_task_status(task_id, callback)
  M.request("sindri/getTaskStatus", { taskId = task_id }, callback)
end

-- Explain code
function M.explain_code(params, callback)
  M.request("sindri/explainCode", {
    code = params.code,
    language = params.language or "auto",
    filePath = params.file_path,
    detailLevel = params.detail_level or "normal",
  }, callback)
end

-- Suggest fix
function M.suggest_fix(params, callback)
  M.request("sindri/suggestFix", {
    code = params.code,
    errorMessage = params.error_message,
    language = params.language or "auto",
    filePath = params.file_path,
  }, callback)
end

-- Generate tests
function M.generate_tests(params, callback)
  M.request("sindri/generateTests", {
    code = params.code,
    language = params.language or "auto",
    filePath = params.file_path,
    testFramework = params.test_framework,
  }, callback)
end

-- Refactor code
function M.refactor_code(params, callback)
  M.request("sindri/refactorCode", {
    code = params.code,
    refactorType = params.refactor_type,
    language = params.language or "auto",
    filePath = params.file_path,
    options = params.options or {},
  }, callback)
end

-- List agents
function M.list_agents(callback)
  M.request("sindri/listAgents", {}, callback)
end

-- Get agent info
function M.get_agent_info(name, callback)
  M.request("sindri/getAgentInfo", { name = name }, callback)
end

-- List sessions
function M.list_sessions(params, callback)
  M.request("sindri/listSessions", {
    limit = params.limit or 20,
  }, callback)
end

-- Get session
function M.get_session(session_id, callback)
  M.request("sindri/getSession", { sessionId = session_id }, callback)
end

-- Analyze file
function M.analyze_file(file_path, callback)
  M.request("sindri/analyzeFile", { filePath = file_path }, callback)
end

-- Get symbols
function M.get_symbols(file_path, callback)
  M.request("sindri/getSymbols", { filePath = file_path }, callback)
end

-- Find references
function M.find_references(symbol_name, path, callback)
  M.request("sindri/findReferences", {
    symbolName = symbol_name,
    path = path,
  }, callback)
end

return M
