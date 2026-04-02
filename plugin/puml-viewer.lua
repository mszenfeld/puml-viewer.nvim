if vim.g.loaded_puml_viewer then
	return
end
vim.g.loaded_puml_viewer = true

local puml = require("puml-viewer")

vim.api.nvim_create_user_command("PumlPreview", puml.cmd_preview, {
	desc = "Start PlantUML preview server and open browser",
})

vim.api.nvim_create_user_command("PumlExport", puml.cmd_export, {
	nargs = "?",
	complete = function()
		return { "png", "svg" }
	end,
	desc = "Export PlantUML diagram to PNG or SVG",
})

vim.api.nvim_create_user_command("PumlStop", puml.cmd_stop, {
	desc = "Stop PlantUML preview server",
})

local group = vim.api.nvim_create_augroup("PumlViewer", { clear = true })

vim.api.nvim_create_autocmd("BufWritePost", {
	group = group,
	pattern = { "*.puml", "*.plantuml", "*.pu", "*.uml", "*.iuml" },
	callback = function()
		local server = require("puml-viewer.server")
		if server.is_running() then
			local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
			local filepath = vim.fn.expand("%:p")
			server.send_update(content, filepath ~= "" and filepath or nil)
		end
	end,
	desc = "Send buffer content to PlantUML preview server on save",
})

vim.api.nvim_create_autocmd("VimLeavePre", {
	group = group,
	callback = function()
		local server = require("puml-viewer.server")
		server.stop()
	end,
	desc = "Stop PlantUML preview server on exit",
})
