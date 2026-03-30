local config = require("puml-viewer.config")
local server = require("puml-viewer.server")
local export = require("puml-viewer.export")

local M = {}

local current_config = nil

--- Check if the current buffer is a PlantUML file.
---@return boolean
local function is_plantuml_file()
  return vim.bo.filetype == "plantuml"
end

--- Validate that required dependencies are available.
---@return boolean
local function validate_dependencies()
  local errors = {}

  if vim.fn.executable("python3") == 0 then
    table.insert(errors, "python3 not found in PATH")
  end

  -- Split command to check just the executable name
  local cmd_parts = vim.split(current_config.plantuml_cmd, " ")
  if vim.fn.executable(cmd_parts[1]) == 0 then
    table.insert(errors, current_config.plantuml_cmd .. " not found in PATH")
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

--- Start preview server and open browser.
local function cmd_preview()
  if not is_plantuml_file() then
    vim.notify("puml-viewer: not a PlantUML file", vim.log.levels.WARN)
    return
  end

  local port = server.get_port()

  if not port then
    port = server.start(current_config)
    if not port then
      return
    end
  end

  -- Send current buffer content
  local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
  server.send_update(content)

  -- Open browser
  local url = "http://localhost:" .. port
  local browser_cmd = current_config.browser_cmd or detect_browser_cmd()

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

--- Export diagram to file.
---@param args table Command arguments from nvim_create_user_command
local function cmd_export(args)
  local format = current_config.export_format
  if args.args ~= "" then
    format = args.args
    if format ~= "png" and format ~= "svg" then
      vim.notify("puml-viewer: invalid format '" .. format .. "'. Use 'png' or 'svg'", vim.log.levels.ERROR)
      return
    end
  end
  export.export(format, current_config)
end

--- Stop the preview server.
local function cmd_stop()
  if server.is_running() then
    server.stop()
    vim.notify("puml-viewer: server stopped", vim.log.levels.INFO)
  end
end

--- Register Ex commands.
local function register_commands()
  vim.api.nvim_create_user_command("PumlPreview", cmd_preview, {
    desc = "Start PlantUML preview server and open browser",
  })

  vim.api.nvim_create_user_command("PumlExport", cmd_export, {
    nargs = "?",
    complete = function()
      return { "png", "svg" }
    end,
    desc = "Export PlantUML diagram to PNG or SVG",
  })

  vim.api.nvim_create_user_command("PumlStop", cmd_stop, {
    desc = "Stop PlantUML preview server",
  })
end

--- Register autocommands.
local function register_autocmds()
  local group = vim.api.nvim_create_augroup("PumlViewer", { clear = true })

  vim.api.nvim_create_autocmd("BufWritePost", {
    group = group,
    pattern = { "*.puml", "*.plantuml", "*.pu", "*.uml", "*.iuml" },
    callback = function()
      if server.is_running() then
        local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
        server.send_update(content)
      end
    end,
    desc = "Send buffer content to PlantUML preview server on save",
  })

  vim.api.nvim_create_autocmd("VimLeavePre", {
    group = group,
    callback = function()
      server.stop()
    end,
    desc = "Stop PlantUML preview server on exit",
  })
end

--- Setup the plugin.
---@param user_opts table|nil User configuration options
function M.setup(user_opts)
  current_config = config.merge(user_opts)

  if not validate_dependencies() then
    return
  end

  -- Register filetype detection for additional extensions
  vim.filetype.add({
    extension = {
      puml = "plantuml",
      pu = "plantuml",
      uml = "plantuml",
      iuml = "plantuml",
    },
  })

  register_commands()
  register_autocmds()
end

return M
