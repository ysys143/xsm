// 시간 제한 없는 자동 분석이 끝난 뒤 전체 함수 목록과 실제 완료 상태를 보존한다.
// @category XSM.Research
import ghidra.app.util.headless.HeadlessScript;
import ghidra.program.model.listing.*;
import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.io.BufferedWriter;
import java.util.*;

public class FullNativeInventory extends HeadlessScript {
    @Override public void run() throws Exception {
        Path output = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(output);
        Gson gson = new GsonBuilder().serializeNulls().create();
        long count = 0;
        try (BufferedWriter writer = Files.newBufferedWriter(output.resolve("functions.jsonl"), StandardCharsets.UTF_8)) {
            FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(true);
            while (iterator.hasNext()) {
                monitor.checkCancelled();
                Function f = iterator.next();
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("entry", f.getEntryPoint().toString());
                row.put("name", f.getName(true));
                row.put("body_addresses", f.getBody().getNumAddresses());
                row.put("external", f.isExternal()); row.put("thunk", f.isThunk());
                writer.write(gson.toJson(row)); writer.newLine(); count++;
            }
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("program", currentProgram.getName());
        summary.put("language", currentProgram.getLanguageID().toString());
        summary.put("analysis_timed_out", analysisTimeoutOccurred());
        summary.put("function_manager_count", currentProgram.getFunctionManager().getFunctionCount());
        summary.put("inventory_rows", count);
        summary.put("source_sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(Paths.get(currentProgram.getExecutablePath())))));
        Files.writeString(output.resolve("summary.json"), new GsonBuilder().setPrettyPrinting().create().toJson(summary) + "\n");
        println("FULL_NATIVE_INVENTORY " + currentProgram.getName() + " rows=" + count + " timed_out=" + summary.get("analysis_timed_out"));
    }
}
