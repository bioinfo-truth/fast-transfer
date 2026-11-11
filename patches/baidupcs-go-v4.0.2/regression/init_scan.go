package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"os"
	"path/filepath"
	"strings"
)

type Package struct {
	ImportPath, Dir string
	GoFiles         []string
}

func main() {
	var list []Package
	b, e := os.ReadFile(os.Args[1])
	if e != nil {
		panic(e)
	}
	if e = json.Unmarshal(b, &list); e != nil {
		panic(e)
	}
	root, _ := filepath.Abs(os.Args[2])
	fs := token.NewFileSet()
	for _, p := range list {
		for _, name := range p.GoFiles {
			path := filepath.Join(p.Dir, name)
			rel, _ := filepath.Rel(root, path)
			if strings.HasPrefix(rel, "..") {
				panic("outside audit root")
			}
			f, e := parser.ParseFile(fs, path, nil, 0)
			if e != nil {
				panic(e)
			}
			for _, d := range f.Decls {
				switch v := d.(type) {
				case *ast.FuncDecl:
					if v.Name.Name == "init" && v.Recv == nil {
						var out bytes.Buffer
						printer.Fprint(&out, fs, v)
						fmt.Printf("INIT %s %s\n%s\n", p.ImportPath, name, out.String())
					}
				case *ast.GenDecl:
					if v.Tok != token.VAR {
						continue
					}
					for _, sp := range v.Specs {
						val := sp.(*ast.ValueSpec)
						for _, expr := range val.Values {
							has := false
							ast.Inspect(expr, func(n ast.Node) bool {
								if _, ok := n.(*ast.CallExpr); ok {
									has = true
								}
								return true
							})
							if has {
								var out bytes.Buffer
								printer.Fprint(&out, fs, val)
								fmt.Printf("VAR %s %s\n%s\n", p.ImportPath, name, out.String())
							}
						}
					}
				}
			}
		}
	}
}
