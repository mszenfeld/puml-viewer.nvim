local defaults = {
  plantuml_cmd = "plantuml",
  server_port = 0,
  browser_cmd = nil,
  default_format = "svg",
  export_format = "png",
  export_dir = nil,
}

local allowed_keys = {}
for k in pairs(defaults) do
  allowed_keys[k] = true
end
-- Keys that default to nil are still valid
allowed_keys["browser_cmd"] = true
allowed_keys["export_dir"] = true

local function merge(user_opts)
  user_opts = user_opts or {}
  local merged = vim.deepcopy(defaults)
  for key, value in pairs(user_opts) do
    if not allowed_keys[key] then
      error("Unknown config option: " .. key)
    end
    merged[key] = value
  end
  return merged
end

local function get_defaults()
  return vim.deepcopy(defaults)
end

return {
  defaults = defaults,
  merge = merge,
  get_defaults = get_defaults,
}
