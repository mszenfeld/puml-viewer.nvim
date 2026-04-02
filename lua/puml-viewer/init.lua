local config = require("puml-viewer.config")
local server = require("puml-viewer.server")
local export = require("puml-viewer.export")
local utils = require("puml-viewer.utils")

local M = {}

-- Config is available immediately with defaults.
-- setup() overrides it with user options.
M.config = config.merge()

--- Validate that required dependencies are available.
---@return boolean
local function validate_dependencies()
  local errors = {}

  if vim.fn.executable("python3") == 0 then
    table.insert(errors, "python3 not found in PATH")
  end

  -- Split command to check just the executable name
  -- (supports both string and table forms with proper quoting)
  local cmd_parts = utils.shell_split(M.config.plantuml_cmd)
  if vim.fn.executable(cmd_parts[1]) == 0 then
    local cmd_display = type(M.config.plantuml_cmd) == "table"
      and table.concat(M.config.plantuml_cmd, " ")
      or M.config.plantuml_cmd
    table.insert(errors, cmd_display .. " not found in PATH")
  end

  if #errors > 0 then
    for _, err in ipairs(errors) do
      vim.notify("puml-viewer: " .. err, vim.log.levels.ERROR)
    end
    return false
  end

  return true
end

--- Detect browser open command for the current platform.
---@return string|nil
local function detect_browser_cmd()
  if vim.fn.executable("open") == 1 then
    return "open" -- macOS
  elseif vim.fn.executable("xdg-open") == 1 then
    return "xdg-open" -- Linux
  end
  return nil
end

--- Send update and open browser once the server is ready.
---@param port number The port the server is listening on
local function open_preview(port)
  -- Send current buffer content with file path for !include resolution
  local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
  local filepath = vim.fn.expand("%:p")
  server.send_update(content, filepath ~= "" and filepath or nil)

  -- Open browser (include session token for authentication)
  local token = server.get_token()
  local url = "http://localhost:" .. port .. "?token=" .. (token or "")
  local browser_cmd = M.config.browser_cmd or detect_browser_cmd()

  if not browser_cmd then
    vim.notify("puml-viewer: no browser command found. Set browser_cmd in config.\nServer running at: " .. url, vim.log.levels.WARN)
    return
  end

  vim.fn.jobstart({ browser_cmd, url }, {
    on_exit = function(_, exit_code)
      if exit_code ~= 0 then
        vim.schedule(function()
          vim.notify("puml-viewer: failed to open browser. Server at: " .. url, vim.log.levels.WARN)
        end)
      end
    end,
  })
end

--- Start preview server and open browser.
function M.cmd_preview()
  if not utils.is_plantuml_file() then
    vim.notify("puml-viewer: not a PlantUML file", vim.log.levels.WARN)
    return
  end

  if not validate_dependencies() then
    return
  end

  local port = server.get_port()

  if port then
    open_preview(port)
    return
  end

  server.start(M.config, function(ready_port)
    open_preview(ready_port)
  end)
end

--- Export diagram to file.
---@param args table Command arguments from nvim_create_user_command
function M.cmd_export(args)
  if not validate_dependencies() then
    return
  end

  local format = M.config.export_format
  if args.args ~= "" then
    format = args.args
    if format ~= "png" and format ~= "svg" then
      vim.notify("puml-viewer: invalid format '" .. format .. "'. Use 'png' or 'svg'", vim.log.levels.ERROR)
      return
    end
  end
  export.export(format, M.config)
end

--- Stop the preview server.
function M.cmd_stop()
  if server.is_running() then
    server.stop()
    vim.notify("puml-viewer: server stopped", vim.log.levels.INFO)
  end
end

--- Setup the plugin with user options.
--- Optional — the plugin works with defaults if never called.
---@param user_opts table|nil User configuration options
function M.setup(user_opts)
  M.config = config.merge(user_opts)
end

return M
